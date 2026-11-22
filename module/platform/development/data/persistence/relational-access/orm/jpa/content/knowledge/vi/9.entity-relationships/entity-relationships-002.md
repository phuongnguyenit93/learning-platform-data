# Phân biệt quan hệ đơn hướng và hai hướng

Trong Java, quan hệ giữa các đối tượng thường được biểu diễn bằng **tham chiếu** hoặc **collection**. Ví dụ, một cuốn sách có thể biết tác giả của nó thông qua `book.getAuthor()`; một tác giả cũng có thể biết danh sách sách của mình qua `author.getBooks()`. Nhưng việc Java cho phép đi từ đối tượng này sang đối tượng kia theo một hay hai chiều **không đồng nghĩa** với việc cơ sở dữ liệu phải có một hay hai khóa ngoại.

Đó là khác biệt trung tâm giữa **quan hệ đơn hướng** (*unidirectional association*) và **quan hệ hai hướng** (*bidirectional association*) trong JPA/Jakarta Persistence:

- **Đơn hướng:** chỉ một phía có thuộc tính cho phép điều hướng sang phía còn lại.
- **Hai hướng:** cả hai phía đều có thuộc tính biểu diễn **cùng một quan hệ**, nhờ đó mã Java có thể điều hướng theo hai chiều.

Trong ánh xạ JPA, ta còn phải phân biệt thêm **phía sở hữu quan hệ** (*owning side*) và **phía đối ứng** (*inverse/non-owning side*). Phân biệt đúng ba khái niệm này giúp tránh những lỗi phổ biến như cập nhật collection nhưng khóa ngoại không đổi, tạo ra hai quan hệ SQL ngoài ý muốn, hay để hai phía của đồ thị đối tượng có trạng thái mâu thuẫn.

Bài học nằm trong chương **Quan hệ thực thể** của chủ đề **Data Persistence, Relational Access, ORM và JPA**. Các ví dụ sử dụng annotation của `jakarta.persistence`; dự án JPA cũ có thể sử dụng package `javax.persistence` tương ứng.

## 1. Bắt đầu từ mô hình: một quan hệ, hai cách nhìn

Giả sử có hai entity:

- `Author`: tác giả.
- `Book`: sách.

Một tác giả có thể viết nhiều sách; mỗi sách trong ví dụ có thể liên kết với một tác giả.

Ở góc nhìn dữ liệu quan hệ, bảng có thể là:

**`authors`**

| id | name |
| ---: | --- |
| 1 | An |
| 2 | Bình |

**`books`**

| id | title | author_id |
| ---: | --- | ---: |
| 101 | Java căn bản | 1 |
| 102 | JPA thực hành | 1 |
| 103 | SQL cho ứng dụng | 2 |

`books.author_id` là **khóa ngoại** trỏ đến `authors.id`. Cấu trúc này cho phép truy vấn theo cả hai chiều:

```sql
-- Từ sách tìm tác giả:
SELECT a.*
FROM authors a
JOIN books b ON b.author_id = a.id
WHERE b.id = 101;

-- Từ tác giả tìm danh sách sách:
SELECT b.*
FROM books b
WHERE b.author_id = 1;
```

Cơ sở dữ liệu không yêu cầu hai khóa ngoại đối ứng để thực hiện hai truy vấn này. Hệ quản trị quan hệ có thể lọc và `JOIN` dựa trên các cột hiện có.

Trong mô hình object, ta quyết định muốn có thuộc tính nào:

```text
ĐƠN HƯỚNG (Book → Author)

Book
  └── author ──────────> Author

Có thể: book.getAuthor()
Không có: author.getBooks() nếu class Author không khai báo


HAI HƯỚNG (Book ↔ Author)

Book ────── author ──────> Author
  ^                           │
  └──────── books ────────────┘

Có thể: book.getAuthor()
Có thể: author.getBooks()
```

**Chiều của association là đặc điểm của mô hình đối tượng và mapping JPA**, không phải “chiều mà SQL được phép truy vấn”. Một quan hệ Java đơn hướng vẫn có thể được truy vấn ngược bằng JPQL/SQL nếu câu truy vấn được viết phù hợp.

## 2. Bảng so sánh tổng quan

| Tiêu chí | Quan hệ đơn hướng | Quan hệ hai hướng |
| --- | --- | --- |
| Điều hướng trong Java | A → B, hoặc B → A | A ↔ B |
| Thuộc tính tham chiếu | Chỉ class ở phía điều hướng khai báo association | Cả hai class đều khai báo association |
| Mapping JPA | Một phía được ánh xạ | Hai phía được ánh xạ và liên kết bằng `mappedBy` ở phía đối ứng |
| Phía sở hữu | Phía duy nhất khai báo quan hệ là phía quản lý association trong mapping | Phải xác định **một owning side** và một inverse side |
| Cập nhật object graph | Ít thuộc tính phải giữ đồng bộ | Ứng dụng cần giữ hai phía nhất quán trong bộ nhớ |
| Khả năng truy vấn ngược | Dùng query; không thể gọi getter ngược nếu không có thuộc tính | Có thể điều hướng qua getter ở cả hai phía |
| Độ phức tạp code | Thường ít hơn | Thường nhiều helper method và quy ước hơn |
| Nguy cơ vòng tham chiếu | Thấp hơn | Dễ gặp khi `toString()`, JSON serialization, `equals()` |
| SQL/schema | Phụ thuộc loại quan hệ và annotation | Thường có thể dùng cùng schema với ánh xạ đơn hướng tương ứng |
| Khi thích hợp | Nghiệp vụ chỉ cần đi theo một chiều | Use case cần đi cả hai chiều và lợi ích rõ ràng |

Không phải mọi quan hệ hai hướng đều tốn thêm bảng. Với `Book.author` và `Author.books`, cả hai mapping có thể dùng **cùng một khóa ngoại `books.author_id`**.

## 3. Quan hệ nhiều-một đơn hướng với `@ManyToOne`

Đây là ví dụ đơn hướng đơn giản và thường gặp: `Book` biết `Author`, nhưng `Author` không khai báo collection sách.

**`Author.java`**

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
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name");
        }
        this.name = name.trim();
    }

    public Long getId() { return id; }
    public String getName() { return name; }
}
```

**`Book.java`**

```java
import jakarta.persistence.*;

@Entity
@Table(name = "books")
public class Book {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 200)
    private String title;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "author_id")
    private Author author;

    protected Book() {}

    public Book(String title, Author author) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title");
        }
        this.title = title.trim();
        this.author = author;
    }

    public Long getId() { return id; }
    public String getTitle() { return title; }
    public Author getAuthor() { return author; }
    public void setAuthor(Author author) { this.author = author; }
}
```

Trong ví dụ:

- `@ManyToOne` nói rằng **nhiều Book có thể tham chiếu cùng một Author**.
- `@JoinColumn(name = "author_id")` nói quan hệ được lưu thông qua cột khóa ngoại của bảng `books`.
- `FetchType.LAZY` mô tả ý định hoãn tải tham chiếu, với cơ chế thực thi phụ thuộc provider.
- `Author` không có `List<Book>`, nên không thể viết `author.getBooks()`.
- `Book` là phía duy nhất khai báo quan hệ; cập nhật `book.setAuthor(author)` trên managed entity là cách thông thường để đổi association.

Ví dụ điều hướng:

```java
Book book = entityManager.find(Book.class, 101L);

Author author = book.getAuthor();
System.out.println(author.getName());
```

Từ `Author` muốn lấy sách, ta vẫn có thể viết JPQL:

```java
List<Book> books = entityManager.createQuery(
    "SELECT b FROM Book b WHERE b.author.id = :authorId",
    Book.class
).setParameter("authorId", 1L)
 .getResultList();
```

Nên hiểu đúng: **“đơn hướng” không có nghĩa là chỉ tra cứu dữ liệu được một chiều**. Nó chỉ có nghĩa class `Author` không chứa thuộc tính đối ứng để điều hướng trực tiếp trong object graph.

### Cập nhật quan hệ trong database

Giả sử `Book #101` đang liên kết `Author #1`, muốn đổi sang `Author #2`:

```java
Book book = entityManager.find(Book.class, 101L);
Author newAuthor = entityManager.find(Author.class, 2L);

book.setAuthor(newAuthor);
// Nếu book được quản lý và giao dịch commit thành công,
// provider đồng bộ khóa ngoại tương ứng.
```

SQL tương đương về mặt ý nghĩa:

```sql
UPDATE books
SET author_id = 2
WHERE id = 101;
```

JPA provider quyết định thời điểm phát SQL theo `flush`/transaction. Getter và setter Java không nhất thiết thực hiện câu SQL ngay lập tức.

## 4. Quan hệ một-nhiều hai hướng: `@OneToMany` kết hợp `@ManyToOne`

Giờ yêu cầu nghiệp vụ mở rộng: ngoài việc từ sách tìm tác giả, ta muốn từ tác giả lấy danh sách sách qua `author.getBooks()`.

Cách thông dụng là **giữ `Book.author` làm phía sở hữu** và thêm `Author.books` làm phía đối ứng.

**`Author.java`**

```java
import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

@Entity
@Table(name = "authors")
public class Author {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    @OneToMany(mappedBy = "author")
    private List<Book> books = new ArrayList<>();

    protected Author() {}

    public Author(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name");
        }
        this.name = name.trim();
    }

    public Long getId() { return id; }
    public String getName() { return name; }

    public List<Book> getBooks() {
        return Collections.unmodifiableList(books);
    }

    public void addBook(Book book) {
        if (book == null) throw new IllegalArgumentException("book");
        book.setAuthor(this);
    }

    public void removeBook(Book book) {
        if (book != null && book.getAuthor() == this) {
            book.setAuthor(null);
        }
    }

    // Chỉ gọi từ Book.setAuthor() để giữ hai phía nhất quán.
    void attachBook(Book book) {
        if (!books.contains(book)) books.add(book);
    }

    void detachBook(Book book) {
        books.remove(book);
    }
}
```

**`Book.java`**

```java
import jakarta.persistence.*;

@Entity
@Table(name = "books")
public class Book {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 200)
    private String title;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "author_id")
    private Author author;

    protected Book() {}

    public Book(String title) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title");
        }
        this.title = title.trim();
    }

    public Long getId() { return id; }
    public String getTitle() { return title; }
    public Author getAuthor() { return author; }

    public void setAuthor(Author newAuthor) {
        if (this.author == newAuthor) return;

        Author oldAuthor = this.author;
        this.author = newAuthor; // Phía sở hữu FK.

        if (oldAuthor != null) {
            oldAuthor.detachBook(this);
        }
        if (newAuthor != null) {
            newAuthor.attachBook(this);
        }
    }
}
```

Trong code trên, `Book.setAuthor()` là điểm tập trung để đồng bộ hai phía. Ví dụ này **cho phép sách không có tác giả** (khóa ngoại `author_id` được phép `NULL`), nên `removeBook()` chỉ bỏ liên kết mà không xóa bản ghi `Book`.

Nếu nghiệp vụ yêu cầu sách **luôn có tác giả**, cần thay đổi mapping thành `optional = false`/`nullable = false` cùng ràng buộc DB, đồng thời thay `removeBook()` bằng hành vi phù hợp như **chuyển sang tác giả khác** hoặc **xóa sách** theo chính sách nghiệp vụ. Không nên vừa cấm khóa ngoại `NULL` vừa cung cấp thao tác “remove link” chỉ đặt `author = null` rồi kỳ vọng flush luôn thành công.

### Cách điều hướng sau khi ánh xạ hai hướng

```java
Author author = entityManager.find(Author.class, 1L);

for (Book book : author.getBooks()) {
    System.out.println(book.getTitle());
}

Book book = entityManager.find(Book.class, 101L);
System.out.println(book.getAuthor().getName());
```

Cả hai lối điều hướng đều đã tồn tại trong Java. Cơ sở dữ liệu vẫn có thể chỉ cần:

```text
authors(id, name)
books(id, title, author_id → authors.id)
```

**Thêm `Author.books` không tự tạo ra khóa ngoại ngược trong bảng `authors`.** `mappedBy = "author"` báo cho provider rằng association ở `Author.books` là mặt đối ứng của thuộc tính `Book.author`.

## 5. Phân biệt hướng điều hướng và phía sở hữu

Đây là điểm quan trọng nhất khi làm việc với quan hệ hai hướng.

### 5.1. Phía sở hữu là gì?

JPA cần xác định phía nào **định nghĩa và điều khiển việc ánh xạ liên kết** vào cột khóa ngoại hoặc bảng nối. Phía đó là *owning side*.

Với ví dụ `Author`–`Book`:

```text
Author.books
    @OneToMany(mappedBy = "author")
           │
           │ phía đối ứng (inverse)
           ▼
Book.author
    @ManyToOne
    @JoinColumn(name = "author_id")
           │
           │ phía sở hữu (owning)
           ▼
books.author_id → authors.id
```

Trong mapping hai hướng một-nhiều/nhiều-một, phía **`@ManyToOne` là owning side** theo mô hình chuẩn của JPA. Phía `@OneToMany(mappedBy = "...")` là inverse side.

### 5.2. `mappedBy` tham chiếu tên thuộc tính Java

Ví dụ đúng:

```java
// Trong Author:
@OneToMany(mappedBy = "author")
private List<Book> books;

// Trong Book:
@ManyToOne
@JoinColumn(name = "author_id")
private Author author;
```

Trong `mappedBy = "author"`, chuỗi `author` là **tên field/property của Book**, không phải tên cột `author_id` và cũng không phải tên bảng `authors`.

Ví dụ sai:

```java
@OneToMany(mappedBy = "author_id") // Sai nếu Book không có property author_id.
private List<Book> books;
```

Nếu tham chiếu sai tên thuộc tính, provider có thể báo lỗi mapping khi khởi động persistence unit.

### 5.3. Có hai phía không có nghĩa có hai owning side

Không nên khai báo cả hai phía như hai quan hệ độc lập nếu ý định là một association hai hướng.

Ví dụ gây nhầm lẫn:

```java
// Trong Author:
@OneToMany
@JoinColumn(name = "author_id")
private List<Book> books;

// Trong Book:
@ManyToOne
@JoinColumn(name = "author_id")
private Author author;
```

Đây **không phải** cách khai báo chuẩn cho một association hai hướng `mappedBy`. Cả hai mapping cùng đưa ra thông tin sở hữu cột và có thể dẫn đến xung đột cấu hình, ghi SQL ngoài ý muốn hoặc cách provider diễn giải không phù hợp ý định.

Cách an toàn là chỉ định rõ:

```java
// Inverse side:
@OneToMany(mappedBy = "author")
private List<Book> books;

// Owning side:
@ManyToOne
@JoinColumn(name = "author_id")
private Author author;
```

### 5.4. Phía sở hữu khác với “chủ sở hữu nghiệp vụ”

Trong Domain-Driven Design, một aggregate root có thể điều khiển nghiệp vụ tạo/xóa entity con. Điều đó **không buộc** aggregate root phải là owning side của khóa ngoại theo JPA.

Ví dụ `Order` là aggregate root và có method `addLine()`, nhưng trong association hai hướng `Order`–`OrderLine`, cột `order_lines.order_id` vẫn thường được ánh xạ bởi `OrderLine.order` ở phía `@ManyToOne`.

**Quyền sở hữu nghiệp vụ, quyền điều hướng đối tượng và quyền sở hữu mapping JPA là ba khái niệm khác nhau.**

## 6. Vì sao phải đồng bộ cả hai phía trong bộ nhớ?

JPA provider quản lý việc đồng bộ trạng thái persistent với database, nhưng **không có hợp đồng tổng quát rằng nó sẽ tự sửa mọi tham chiếu Java ở phía đối ứng ngay sau khi ta đổi phía sở hữu**.

Giả sử:

```java
Book book = entityManager.find(Book.class, 101L);
Author oldAuthor = book.getAuthor();
Author newAuthor = entityManager.find(Author.class, 2L);

book.setAuthor(newAuthor); // Nếu đây là setter chỉ gán field.
```

Nếu setter chỉ chạy `this.author = newAuthor`, thì `oldAuthor.getBooks()` có thể vẫn chứa `book` trong cùng object graph đã nạp; `newAuthor.getBooks()` cũng có thể chưa có `book`.

Phía sở hữu `Book.author` đã đổi, nên database có thể được cập nhật đúng sau `flush`. Nhưng **đồ thị object trong bộ nhớ đang mâu thuẫn**:

```text
book.author = newAuthor

oldAuthor.books vẫn có book      ← chưa đồng bộ
newAuthor.books chưa có book       ← chưa đồng bộ
```

Ngược lại, nếu chỉ làm:

```java
newAuthor.getBooks().add(book);
```

mà không gán `book.author = newAuthor`, thay đổi ở **inverse side** không phải là cách chuẩn để cập nhật khóa ngoại `books.author_id`.

### Quy tắc helper method

Giải pháp thông thường là đặt thao tác thay đổi association ở một method quản lý nhất quán cả hai phía, như `Book.setAuthor()` trong ví dụ trên, hoặc `Author.addBook()` gọi ngược về `Book.setAuthor()`.

Một luồng chuyển tác giả được biểu diễn:

```text
author2.addBook(book)
        │
        ▼
book.setAuthor(author2)
        │
        ├── oldAuthor.books.remove(book)
        ├── book.author = author2
        └── author2.books.add(book)
                 │
                 ▼
Object graph nhất quán
                 │
                 ▼
JPA flush association qua owning side
                 │
                 ▼
books.author_id = author2.id
```

Helper method phải tránh gọi nhau thành vòng đệ quy vô hạn. Cách tách `attachBook()/detachBook()` nội bộ trong ví dụ chỉ sửa collection, còn `setAuthor()` điều phối cả quá trình.

**Lưu ý về `equals()`:** ví dụ dùng `List.contains()` và `List.remove()`; nếu entity có `equals()/hashCode()` tùy biến, cần bảo đảm quy tắc định danh không gây kết quả bất ngờ. Khi entity xuất hiện ở nhiều persistence context khác nhau, phép so sánh tham chiếu `==` cũng không thay thế so sánh identity nghiệp vụ/khóa chính. Helper trên giả định thao tác với các instance trong cùng object graph đang quản lý.

## 7. Quan hệ một-nhiều đơn hướng có gì khác?

Không phải cứ một tác giả có nhiều sách thì bắt buộc khai báo hai hướng. Có thể để `Author` giữ collection `books`, nhưng `Book` không biết `Author`.

Ví dụ:

```java
@Entity
@Table(name = "authors")
public class Author {
    @Id
    private Long id;

    @OneToMany
    private List<Book> books = new ArrayList<>();

    protected Author() {}

    public List<Book> getBooks() { return books; }
}

@Entity
@Table(name = "books")
public class Book {
    @Id
    private Long id;

    protected Book() {}
}
```

Đây là **`@OneToMany` đơn hướng**: từ `Author` sang `Book`. Không có `Book.author`.

### 7.1. Schema mặc định có thể dùng bảng nối

Với `@OneToMany` đơn hướng **không cấu hình `@JoinColumn`**, JPA thường ánh xạ quan hệ thông qua một **join table** theo quy tắc mặc định của đặc tả:

```text
authors                  author_books             books
  id ────────────────── author_id
                          book_id ──────────────── id
```

Tên bảng và cột thực tế phụ thuộc quy tắc đặt tên/cấu hình; `author_books` chỉ là tên minh họa.

Một schema tương ứng có thể gồm:

```sql
CREATE TABLE authors (
    id BIGINT PRIMARY KEY
);

CREATE TABLE books (
    id BIGINT PRIMARY KEY
);

CREATE TABLE author_books (
    author_id BIGINT NOT NULL REFERENCES authors(id),
    book_id   BIGINT NOT NULL REFERENCES books(id),
    CONSTRAINT uq_author_books_book UNIQUE (book_id)
);
```

Ràng buộc unique trên `book_id` trong ví dụ thể hiện mỗi `Book` chỉ thuộc một `Author` trong quan hệ một-nhiều, nhưng chi tiết DDL mặc định tùy provider và schema generation. Với hệ thống thật, cần tạo khóa/ràng buộc phù hợp và kiểm soát migration.

**Tình huống quan trọng:** chuyển một-nhiều từ đơn hướng sang hai hướng **không nhất thiết chỉ thêm một field**. Nếu mapping đơn hướng cũ dùng join table, còn mapping hai hướng mới dùng foreign key `books.author_id`, schema và dữ liệu phải được migration.

### 7.2. Đơn hướng một-nhiều cũng có thể dùng khóa ngoại ở bảng con

Nếu muốn giữ khóa ngoại ở `books`, có thể khai báo `@JoinColumn` trên phía collection:

```java
@Entity
public class Author {
    @Id
    private Long id;

    @OneToMany
    @JoinColumn(name = "author_id")
    private List<Book> books = new ArrayList<>();

    protected Author() {}
}

@Entity
public class Book {
    @Id
    private Long id;

    protected Book() {}
}
```

Ở đây, quan hệ **vẫn đơn hướng** vì `Book` không có `author`; annotation `@JoinColumn` chỉ chỉ ra nơi lưu liên kết. `Author.books` là phía điều khiển association trong mapping đơn hướng này.

Schema minh họa:

```text
authors(id)
books(id, author_id → authors.id)
```

Về cấu trúc bảng, nó có thể giống schema của quan hệ hai hướng `Author.books ↔ Book.author`, nhưng API object và quyền sở hữu mapping vẫn khác.

**Hệ quả thực tế:** một-nhiều đơn hướng với foreign key ở bảng con có thể khiến provider cần các câu `UPDATE` bổ sung hoặc thứ tự thao tác SQL khác, tùy chiến lược sinh khóa và implementation. Không nên suy rằng số lệnh SQL giống hệt cách hai hướng chỉ vì schema giống nhau; hãy xem SQL thực tế khi hiệu năng là yêu cầu.

## 8. Quan hệ một-một đơn hướng và hai hướng

Quan hệ một-một thường gặp giữa `UserAccount` và `UserProfile`. Cũng có thể ánh xạ đơn hướng hoặc hai hướng.

### 8.1. Đơn hướng: tài khoản biết hồ sơ

```java
@Entity
public class UserAccount {
    @Id
    private Long id;

    @OneToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "profile_id", unique = true)
    private UserProfile profile;

    protected UserAccount() {}

    public UserProfile getProfile() { return profile; }
}

@Entity
public class UserProfile {
    @Id
    private Long id;

    protected UserProfile() {}
}
```

Lúc này chỉ có `account.getProfile()`. `UserProfile` không có `getAccount()`.

Một schema quan hệ có thể là:

```text
user_account(id, profile_id UNIQUE → user_profile.id)
user_profile(id)
```

`unique = true` diễn đạt tính duy nhất tại metadata mapping; cần có unique constraint thực tế trong database để bảo vệ dữ liệu trước các đường ghi khác.

### 8.2. Hai hướng: hồ sơ cũng biết tài khoản

Ta bổ sung phía đối ứng:

```java
@Entity
public class UserProfile {
    @Id
    private Long id;

    @OneToOne(mappedBy = "profile")
    private UserAccount account;

    protected UserProfile() {}

    public UserAccount getAccount() { return account; }

    void setAccountInternal(UserAccount account) {
        this.account = account;
    }
}
```

Trong `UserAccount`, phía sở hữu vẫn là `profile` với `@JoinColumn`:

```java
@OneToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "profile_id", unique = true)
private UserProfile profile;

public void setProfile(UserProfile newProfile) {
    if (this.profile == newProfile) return;

    UserProfile previous = this.profile;
    this.profile = newProfile;

    if (previous != null && previous.getAccount() == this) {
        previous.setAccountInternal(null);
    }
    if (newProfile != null) {
        newProfile.setAccountInternal(this);
    }
}
```

Ví dụ helper này giả định `newProfile` chưa được liên kết với một tài khoản khác. Trong code production cần kiểm tra invariant “một profile chỉ thuộc một account”, xử lý quan hệ cũ và constraint DB khi chuyển profile từ account khác, thay vì cho phép trạng thái mâu thuẫn. Một ứng dụng có thể áp đặt điều kiện `newProfile.getAccount() == null` hoặc xây dựng thao tác thay thế/di chuyển có kiểm soát.

Với quan hệ một-một, **bên có khóa ngoại/`@JoinColumn` thường là owning side**, còn phía dùng `mappedBy` là inverse side. Không được giả định phía có field tên “account” luôn là owning side; phải đọc mapping thực tế.

### 8.3. Shared primary key và `@MapsId`

Một-một còn có thể được thiết kế để hai entity dùng chung khóa chính bằng `@MapsId`. Khi đó việc xác định phía sở hữu và quy tắc tạo ID phụ thuộc mapping cụ thể. Đây là biến thể schema khác với `profile_id UNIQUE`; sự phân biệt **đơn hướng/hai hướng vẫn là về thuộc tính điều hướng trong Java**, dù khóa quan hệ được biểu diễn ra sao.

## 9. Quan hệ nhiều-nhiều đơn hướng và hai hướng

Giả sử `Student` có thể đăng ký nhiều `Course` và mỗi `Course` có nhiều `Student`.

### 9.1. Đơn hướng nhiều-nhiều

Chỉ `Student` biết danh sách khóa học:

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

    protected Student() {}
}

@Entity
public class Course {
    @Id
    private Long id;

    protected Course() {}
}
```

Cơ sở dữ liệu dùng bảng nối:

```sql
CREATE TABLE student_courses (
    student_id BIGINT NOT NULL REFERENCES students(id),
    course_id  BIGINT NOT NULL REFERENCES courses(id),
    PRIMARY KEY (student_id, course_id)
);
```

Tên `students` và `courses` ở SQL là minh họa; entity có thể dùng `@Table(name = "...")` để cố định tên tương ứng. Bảng nối lưu các cặp khóa, không lưu một danh sách đối tượng trong một ô.

### 9.2. Hai hướng nhiều-nhiều

Bổ sung `Course.students` làm phía đối ứng:

```java
// Trong Student — owning side:
@ManyToMany
@JoinTable(
    name = "student_courses",
    joinColumns = @JoinColumn(name = "student_id"),
    inverseJoinColumns = @JoinColumn(name = "course_id")
)
private Set<Course> courses = new HashSet<>();

// Trong Course — inverse side:
@ManyToMany(mappedBy = "courses")
private Set<Student> students = new HashSet<>();
```

Ở đây, **một phía được chọn làm owning side**, phía còn lại dùng `mappedBy`. Với nhiều-nhiều, không có quy tắc “phía many là chủ sở hữu” vì **cả hai phía đều là many**; nhóm phát triển phải chọn rõ một phía làm chủ mapping bảng nối.

Lưu ý `mappedBy = "courses"` là tên field trong `Student`.

Ví dụ helper để đồng bộ hai phía:

```java
// Trong Student:
public void enroll(Course course) {
    if (course == null) throw new IllegalArgumentException("course");
    if (courses.add(course)) {
        course.attachStudent(this);
    }
}

public void withdraw(Course course) {
    if (course != null && courses.remove(course)) {
        course.detachStudent(this);
    }
}

// Trong Course (package-private helpers):
void attachStudent(Student student) {
    students.add(student);
}

void detachStudent(Student student) {
    students.remove(student);
}
```

Cách dùng:

```java
student.enroll(course);
student.withdraw(course);
```

`Set` cần `equals()/hashCode()` ổn định phù hợp với entity identity. Đặc biệt, nếu hash code dựa trên ID do DB sinh sau `persist()`, phần tử có thể đổi hash sau khi đã nằm trong `HashSet`. Khi thiết kế entity JPA có `Set`, cần thống nhất quy tắc equality để tránh lỗi collection. Ví dụ trên tập trung vào đồng bộ hướng quan hệ; không ấn định một chiến lược equality cụ thể cho mọi dự án.

### 9.3. Không tùy tiện cascade remove ở nhiều-nhiều

`Student` và `Course` thường có vòng đời độc lập. Việc hủy đăng ký nên xóa **liên kết trong bảng nối**, không xóa bản ghi `Course` mà nhiều sinh viên khác còn sử dụng.

Vì thế, không nên gắn `cascade = CascadeType.REMOVE` hoặc `CascadeType.ALL` một cách máy móc vào `@ManyToMany`. Phân biệt:

- **Xóa liên kết** `student_courses(student_id, course_id)`.
- **Xóa entity Course** khỏi bảng `courses`.

Hai thao tác có ý nghĩa nghiệp vụ hoàn toàn khác nhau.

Nếu việc đăng ký có dữ liệu riêng như `enrolledAt`, `grade` hoặc `status`, thường nên mô hình hóa **Enrollment** thành entity riêng với hai quan hệ `@ManyToOne`, thay vì dùng `@ManyToMany` thuần túy. Mô hình hai hướng hay đơn hướng vẫn có thể được quyết định tại các association đó.

## 10. Cascade và orphan removal không quyết định chiều của quan hệ

Hai khái niệm dễ bị trộn lẫn với đơn hướng/hai hướng là **cascade** và **orphan removal**.

- `cascade` điều khiển thao tác vòng đời entity như `PERSIST`, `MERGE`, `REMOVE` được lan truyền sang entity liên quan theo mapping.
- `orphanRemoval = true` biểu thị rằng entity con bị gỡ khỏi quan hệ sở hữu riêng có thể được xóa khi provider đồng bộ trạng thái theo quy tắc JPA.
- **Đơn hướng/hai hướng** chỉ mô tả hướng điều hướng trong mô hình object.

Ví dụ tổng thể đơn hàng:

```java
@Entity
public class PurchaseOrder {
    @Id
    @GeneratedValue
    private Long id;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    public void addLine(OrderLine line) {
        if (line == null) throw new IllegalArgumentException("line");
        if (line.getOrder() != null) {
            throw new IllegalStateException("Line already belongs to an order");
        }
        lines.add(line);
        line.attachTo(this);
    }

    public void removeLine(OrderLine line) {
        if (line != null && lines.remove(line)) {
            line.detach();
        }
    }
}

@Entity
public class OrderLine {
    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    protected OrderLine() {}

    public PurchaseOrder getOrder() {
        return order;
    }

    void attachTo(PurchaseOrder order) {
        this.order = order;
    }

    void detach() {
        this.order = null;
    }
}
```

Giả định ở ví dụ này, `OrderLine` là entity con thuộc vòng đời của `PurchaseOrder`, và loại khỏi `lines` có nghĩa **xóa dòng hàng** chứ không phải giữ một dòng hàng không có đơn. `orphanRemoval = true` phù hợp với giả định đó. Nếu quan hệ chỉ là tham chiếu có thể thay đổi mà entity con phải tiếp tục tồn tại, `orphanRemoval` có thể không thích hợp.

`cascade = ALL` trên `PurchaseOrder.lines` có thể được dùng dù phía collection là **inverse side** của quan hệ hai hướng. Quy tắc cascade **không biến phía đó thành owning side** của khóa ngoại. Vì vậy cần xử lý hai khái niệm riêng: ai giữ foreign key, và thao tác lifecycle nào lan truyền.

## 11. `mappedBy` không tương đương `@JoinColumn`

So sánh trực tiếp:

| Annotation | Đặt ở đâu? | Ý nghĩa chính |
| --- | --- | --- |
| `@JoinColumn(name = "author_id")` | Phía định nghĩa cột khóa ngoại/quan hệ theo mapping | Liên kết với cột SQL có tên `author_id` |
| `@OneToMany(mappedBy = "author")` | Phía đối ứng của quan hệ hai hướng | Chỉ tới thuộc tính association `Book.author` của owning side |
| `@OneToOne(mappedBy = "profile")` | Phía đối ứng của một-một | Chỉ tới thuộc tính `UserAccount.profile` |
| `@ManyToMany(mappedBy = "courses")` | Phía đối ứng của nhiều-nhiều | Chỉ tới collection `Student.courses` ở owning side |
| `@JoinTable(...)` | Phía sở hữu quan hệ dùng bảng nối | Mô tả bảng nối và các cột tham chiếu |

Sự khác biệt dễ nhớ:

- `@JoinColumn` nói về **liên kết dữ liệu ở schema**.
- `mappedBy` nói về **tên một thuộc tính quan hệ trong Java**, xác định mapping hai phía cùng thuộc một association.
- `mappedBy` không quyết định quan hệ có “lười tải” hay không, không thay thế cascade và không phải tên khóa ngoại.

Đối với quan hệ `@ManyToOne`, phía nhiều là owning side và không dùng `mappedBy` trên annotation `@ManyToOne`. Phía `@OneToMany` đối ứng mới thường khai báo `mappedBy`.

## 12. Một phía và hai phía ảnh hưởng thiết kế API như thế nào?

Một câu hỏi thiết kế tốt là: **Use case nào thật sự cần điều hướng từ B về A?**

Ví dụ nghiệp vụ sách:

- Màn hình chi tiết sách cần tên tác giả: `Book.author` là đủ.
- Màn hình tác giả cần danh sách sách: có thể chọn `Author.books` hai hướng hoặc truy vấn repository theo `authorId`.
- Trang tìm sách theo tác giả có phân trang: truy vấn `SELECT b FROM Book b WHERE b.author.id = :id` có thể đơn giản hơn việc tải toàn bộ `author.books`.
- Giao diện quản trị cần sửa tác giả của sách: phía owning `Book.author` vẫn là nguồn thay đổi khóa ngoại.

Trong nhiều ứng dụng, **không cần ánh xạ hai hướng chỉ để hỗ trợ query ngược**. Repository/JPQL hoàn toàn có thể lấy dữ liệu theo chiều mà không có getter Java tương ứng.

### Khi đơn hướng thường đủ

- Logic nghiệp vụ chủ yếu đi từ entity con tới entity cha, ví dụ `Invoice.customer`.
- Cần tránh mô hình object có tham chiếu vòng hoặc collection rất lớn.
- Chỉ cần truy vấn ngược ở một vài màn hình/báo cáo và có thể dùng query riêng.
- Tách ranh giới aggregate; không muốn entity cha điều hướng trực tiếp tới toàn bộ tập entity con.
- Muốn mapping và các phương thức cập nhật quan hệ đơn giản hơn.

### Khi hai hướng hữu ích

- Nghiệp vụ thường xuyên cần duyệt quan hệ từ cả hai phía **trong cùng object graph**.
- Một aggregate root quản lý các entity con thông qua collection như `order.addLine()`.
- Cần các helper biểu diễn rõ thao tác liên kết/hủy liên kết giữa hai entity.
- Quan hệ có số lượng phần tử và vòng đời phù hợp để quản lý như một collection.
- Khả năng điều hướng hai chiều giúp code domain rõ nghĩa hơn so với nhiều truy vấn độc lập.

Dù chọn cách nào, cần đánh giá tác động của fetch plan và transaction. Có thêm collection trong class không đồng nghĩa nên tải toàn bộ collection khi xử lý một entity.

## 13. Hướng điều hướng không quyết định chiến lược tải

Các yếu tố sau khác nhau:

1. **Direction:** object A có field B hay không?
2. **Ownership:** phía nào quản lý association trong ánh xạ SQL?
3. **Fetch strategy:** khi lấy A, có cần nạp B ngay hay trì hoãn?
4. **Transaction boundary:** khi nào persistence context còn hoạt động?
5. **Cascade:** thay đổi vòng đời của A có lan truyền sang B không?

Ví dụ:

```java
@ManyToOne(fetch = FetchType.LAZY)
private Author author;
```

vẫn là **đơn hướng** nếu chỉ `Book` có field `author`; ngược lại một collection hai hướng:

```java
@OneToMany(mappedBy = "author", fetch = FetchType.LAZY)
private List<Book> books;
```

không trở thành “ít hai hướng hơn” chỉ vì dữ liệu được tải trễ.

Về mặc định trong JPA truyền thống:

| Kiểu quan hệ | Fetch mặc định |
| --- | --- |
| `@ManyToOne` | `EAGER` |
| `@OneToOne` | `EAGER` |
| `@OneToMany` | `LAZY` |
| `@ManyToMany` | `LAZY` |

Mặc định không phải là lời khuyên hiệu năng cho mọi use case. `EAGER` có thể phát sinh nhiều truy vấn hoặc tải dữ liệu không cần thiết; `LAZY` phụ thuộc provider và ranh giới persistence context. Khi cần dữ liệu quan hệ rõ ràng, có thể dùng JPQL `JOIN FETCH`, entity graph hoặc DTO projection.

### Vấn đề N+1

Ví dụ:

```java
List<Author> authors = entityManager.createQuery(
    "SELECT a FROM Author a", Author.class
).getResultList();

for (Author a : authors) {
    System.out.println(a.getBooks().size());
}
```

Với quan hệ hai hướng và collection lazy, thao tác trên có thể phát sinh một query lấy tác giả cộng nhiều query lấy `books`. Việc có thêm hướng điều hướng khiến code **dễ truy cập dữ liệu hơn**, nhưng cũng có thể làm I/O không lộ rõ trong Java.

Một giải pháp tùy use case là truy vấn tập hợp:

```java
List<Object[]> counts = entityManager.createQuery(
    "SELECT a.id, COUNT(b) FROM Author a " +
    "LEFT JOIN a.books b GROUP BY a.id",
    Object[].class
).getResultList();
```

Nếu màn hình chỉ cần số sách, truy vấn aggregate tránh buộc tải từng object `Book`. Với fetch join collection và phân trang, cũng cần chú ý nhân số hàng SQL và giới hạn của provider.

**Không có hướng điều hướng nào bảo đảm hiệu năng tốt hơn chỉ dựa trên số getter.** Hiệu năng phụ thuộc hình dạng truy vấn, index, dữ liệu, provider và cách sử dụng association trong transaction.

## 14. JSON serialization và tham chiếu vòng ở quan hệ hai hướng

Nếu trả JPA entity trực tiếp ra REST API, quan hệ hai hướng có thể gây vòng tham chiếu:

```text
Author
  books[0]
    author
      books[0]
        author
          ...
```

Một serializer có thể gặp đệ quy, output rất lớn, lỗi lazy loading hoặc vô tình đưa nhiều dữ liệu hơn dự kiến ra API.

Ví dụ không nên mặc định:

```java
@GetMapping("/authors/{id}")
public Author getAuthor(@PathVariable Long id) {
    return authorRepository.findById(id).orElseThrow();
}
```

Việc dùng `@JsonIgnore`, `@JsonManagedReference`/`@JsonBackReference` hoặc cấu hình Jackson khác **không phải quy tắc JPA**; đó là cơ chế serialize ở tầng API. Nó có thể giải quyết một số tình huống, nhưng dễ làm mô hình API bị ràng buộc vào ORM.

Một hướng thường rõ ràng hơn là tạo DTO theo nhu cầu endpoint:

```java
public record BookView(Long id, String title) {}

public record AuthorView(
    Long id,
    String name,
    List<BookView> books
) {}
```

Repository/service lấy dữ liệu cần thiết rồi ánh xạ thành DTO. Khi đó JSON không tự điều hướng từ `BookView` về `AuthorView`; cấu trúc phản hồi có chủ đích.

Trong domain object, `toString()` và `equals()/hashCode()` cũng cần cẩn thận với quan hệ hai hướng. Việc in log hoặc so sánh entity không nên vô tình duyệt collection lớn, khởi phát lazy query hoặc tạo vòng lặp.

## 15. Đừng nhầm thay đổi collection với thay đổi DB

Giả sử mapping:

```java
// Trong Author:
@OneToMany(mappedBy = "author")
private List<Book> books;

// Trong Book:
@ManyToOne
@JoinColumn(name = "author_id")
private Author author;
```

Đoạn sau chỉ sửa inverse side:

```java
author.getBooks().add(book);
```

Nếu `book.author` không được cập nhật, provider **không phải coi riêng thao tác đó là cập nhật foreign key** của association hai hướng. Đây là lỗi rất phổ biến vì trong Java collection đã thay đổi, người viết tưởng dữ liệu sẽ được lưu.

Ngược lại:

```java
book.setAuthor(author);
```

nếu đây là setter cập nhật owning side thì có thể dẫn đến thay đổi khóa ngoại khi flush, nhưng object graph của `author.books` vẫn có thể chưa đúng nếu setter không đồng bộ collection.

Nên thực hiện qua helper:

```java
author.addBook(book);
```

với implementation cập nhật **cả hai phía** như ví dụ phần 4. Tạo API công khai cho phép sửa collection trực tiếp có thể khiến người gọi phá vỡ invariant; trả về view không sửa được là một cách hạn chế, nhưng JPA vẫn cần truy cập trường persistent theo mapping.

### `flush()` và `clear()` không thay thế helper

`flush()` đồng bộ persistence context với database; nó không có hợp đồng tự chữa mọi collection đối ứng mà mã Java đã giữ sai. `clear()` làm các entity thành detached trong persistence context hiện tại; khi load lại, provider có thể khôi phục trạng thái từ DB, nhưng việc dùng clear như “cách sửa” không giải quyết lỗi thiết kế của thao tác cập nhật association.

### Bulk update có thể bỏ qua object graph đang quản lý

Giả sử thực hiện:

```java
entityManager.createQuery(
    "UPDATE Book b SET b.author = :newAuthor WHERE b.id = :bookId"
).setParameter("newAuthor", newAuthor)
 .setParameter("bookId", 101L)
 .executeUpdate();
```

Bulk JPQL update có các quy tắc riêng và **không đồng bộ tự động mọi instance managed đang có**. Nếu một `Book` hoặc `Author.books` đã được nạp, chúng có thể tiếp tục giữ state cũ cho tới khi được refresh/clear hoặc thiết kế lại ranh giới persistence context. Điều này càng quan trọng với hai hướng, vì có nhiều biểu diễn trong bộ nhớ cần nhất quán.

## 16. Một hay hai hướng không quyết định bảng SQL có bao nhiêu quan hệ

Cùng một nghiệp vụ “mỗi Book thuộc một Author” có các lựa chọn sau:

| Mapping object | Ví dụ thuộc tính | Schema thường gặp |
| --- | --- | --- |
| `ManyToOne` đơn hướng | `Book.author` | FK `books.author_id` |
| `OneToMany` đơn hướng mặc định | `Author.books` | Join table nối `authors` và `books` |
| `OneToMany` đơn hướng với `@JoinColumn` | `Author.books` | FK `books.author_id` |
| `OneToMany`/`ManyToOne` hai hướng | `Author.books` và `Book.author` | FK `books.author_id` |
| `ManyToMany` đơn hướng | `Student.courses` | Join table `student_courses` |
| `ManyToMany` hai hướng | `Student.courses` và `Course.students` | Cũng join table `student_courses` |

Bảng này cho thấy không thể chỉ dựa vào “đơn hướng” hoặc “hai hướng” để kết luận số bảng hay số foreign key. Còn phải xét **loại quan hệ** và các annotation điều khiển mapping.

Đặc biệt, khi refactor:

```text
Author.books (unidirectional @OneToMany)
            ↓
Author.books + Book.author (bidirectional)
```

cần kiểm tra schema hiện hữu có đang dùng **join table** hay **foreign key ở books**. Nếu quan hệ được chuyển từ join table sang foreign key, dữ liệu liên kết phải được di chuyển tương ứng. Chỉ thêm `mappedBy` và property Java có thể không đủ để tương thích với database cũ.

## 17. Kết hợp với định danh entity và collection

Quan hệ hai hướng thường chứa collection entity. Collection lại phụ thuộc vào cách Java so sánh phần tử.

### 17.1. `List` và `Set` khác nhau

- `List<Book>` cho phép các phần tử có vị trí; `List.contains()` thường dựa vào `equals()` để tìm phần tử.
- `Set<Book>` dùng `equals()/hashCode()` để xác định sự có mặt và tính duy nhất theo semantics Java.
- Database kiểm soát trùng lặp bằng `PRIMARY KEY`/`UNIQUE` và các ràng buộc thực tế, **không phải** phương thức `equals()` của Java.

Nếu `hashCode()` của entity thay đổi khi ID được DB sinh, một entity đang nằm trong `HashSet` có thể gặp hành vi khó đoán khi remove/contains. Vì vậy, lựa chọn collection và chiến lược equality phải cùng nhất quán với vòng đời entity.

### 17.2. Không đồng nhất tham chiếu Java với identity database

Trong cùng persistence context, JPA duy trì một managed entity instance cho identity tương ứng theo quy tắc quản lý entity. Nhưng ở các context khác nhau, cùng hàng DB có thể được đại diện bởi hai Java object khác nhau.

Ví dụ:

```java
Book fromContextA = emA.find(Book.class, 101L);
Book fromContextB = emB.find(Book.class, 101L);

// Hai object có thể khác tham chiếu dù cùng khóa chính.
boolean sameReference = fromContextA == fromContextB;
```

Khi thiết kế helper đồng bộ hai phía, nên thao tác trên các instance có vòng đời rõ ràng; tránh ghép tùy tiện detached entity từ context này vào collection managed của context khác mà chưa hiểu quy tắc `merge` và cascade.

### 17.3. Không áp đặt thứ tự bảng vào collection

`List<Book>` không có nghĩa SQL tự giữ thứ tự nếu schema không có cột vị trí hoặc truy vấn không có `ORDER BY`. Cần dùng cơ chế thích hợp như `@OrderBy` (sắp theo thuộc tính) hoặc `@OrderColumn` (lưu vị trí) tùy yêu cầu.

Hướng đơn/hai chiều không quyết định thứ tự collection.

## 18. Mẫu lỗi thường gặp khi viết quan hệ hai hướng

### Lỗi 1: `mappedBy` dùng tên cột SQL

Sai:

```java
@OneToMany(mappedBy = "author_id")
private List<Book> books;
```

Đúng khi field của `Book` tên `author`:

```java
@OneToMany(mappedBy = "author")
private List<Book> books;
```

### Lỗi 2: Chỉ sửa inverse side

Sai ý định:

```java
author.getBooks().add(book);
// book.author không đổi.
```

Dùng helper bảo đảm cập nhật owning side và collection đối ứng.

### Lỗi 3: Hai phía đều được khai báo là owning mapping

Tránh dùng `@JoinColumn` trên cả hai phía với cùng mục đích ánh xạ một association hai hướng. Xác định một phía sở hữu và dùng `mappedBy` ở phía đối ứng.

### Lỗi 4: Helper gọi nhau vô hạn

Ví dụ:

```java
// Trong Author:
void addBook(Book b) {
    books.add(b);
    b.setAuthor(this);
}

// Trong Book:
void setAuthor(Author a) {
    author = a;
    a.addBook(this); // Gọi lại, có thể đệ quy không dừng.
}
```

Phải thiết kế một method điều phối, những method nội bộ còn lại chỉ cập nhật collection/reference mà không gọi vòng lặp.

### Lỗi 5: Bỏ qua khi chuyển một entity sang owner mới

Nếu sách đã thuộc tác giả A mà chuyển sang B, cần loại khỏi `A.books` và thêm vào `B.books`, đồng thời đặt `book.author = B`. Chỉ thêm vào B có thể khiến sách xuất hiện trong cả hai collection trong bộ nhớ.

### Lỗi 6: Dùng `orphanRemoval` khi chỉ muốn bỏ liên kết

`orphanRemoval = true` có thể dẫn đến xóa entity con thay vì chỉ đặt foreign key `NULL`. Chỉ dùng khi vòng đời của entity con thật sự thuộc về owner tương ứng.

### Lỗi 7: Dùng cascade remove ở nhiều-nhiều

Xóa một `Student` không nên đồng thời xóa các `Course` dùng chung. Thao tác xóa quan hệ khác thao tác xóa entity.

### Lỗi 8: Dùng entity hai hướng làm JSON API trực tiếp

Dễ gây tham chiếu vòng, tải dữ liệu lazy ngoài ý muốn và lộ cấu trúc persistence. DTO theo use case thường an toàn và rõ ràng hơn.

### Lỗi 9: Tưởng `LAZY` hoặc `EAGER` quyết định chiều quan hệ

Fetch type chỉ nói về kế hoạch tải; direction quyết định thuộc tính Java nào cho phép điều hướng.

### Lỗi 10: Bỏ qua migration khi đổi đơn hướng sang hai hướng

Nếu mapping đơn hướng hiện có dùng join table còn mapping hai hướng dùng FK ở bảng con, database có thể cần thay đổi schema và di chuyển dữ liệu; không thể kết luận chỉ sửa hai class là xong.

## 19. Bài tập tình huống: chọn quan hệ phù hợp

### Bài tập 1: Nhận biết đơn hướng

Cho hai class:

```java
@Entity
public class Invoice {
    @Id
    private Long id;

    @ManyToOne
    private Customer customer;

    protected Invoice() {}
}

@Entity
public class Customer {
    @Id
    private Long id;

    protected Customer() {}
}
```

**Câu hỏi:** Quan hệ nào? Có thể lấy hóa đơn của khách hàng không?

**Gợi ý:** Đây là `Invoice → Customer` đơn hướng. Class `Customer` không có `getInvoices()`, nhưng có thể query `Invoice` theo `customer.id`. Không cần bổ sung association hai hướng chỉ vì muốn lấy danh sách hóa đơn trên một màn hình.

### Bài tập 2: Xác định owning side

Cho:

```java
// Department:
@OneToMany(mappedBy = "department")
private List<Employee> employees;

// Employee:
@ManyToOne
@JoinColumn(name = "department_id")
private Department department;
```

**Câu hỏi:** Phía nào quyết định cập nhật `employees.department_id`?

**Đáp án:** `Employee.department` là owning side. `Department.employees` là inverse side nhờ `mappedBy = "department"`. Đổi collection mà không đồng bộ `employee.department` không phải cách chuẩn để sửa khóa ngoại.

### Bài tập 3: Chọn `mappedBy`

```java
// Customer:
@OneToMany(mappedBy = "???")
private List<Address> addresses;

// Address:
@ManyToOne
@JoinColumn(name = "customer_id")
private Customer owner;
```

**Câu hỏi:** Thay `???` bằng gì?

**Đáp án:** `"owner"`, vì đó là tên field association trong `Address`. Không dùng `"customer_id"` vì đó là tên cột SQL.

### Bài tập 4: Hai class có tham chiếu hai chiều nhưng mapping sai

```java
// Order:
@OneToMany
private List<OrderLine> lines;

// OrderLine:
@ManyToOne
private Order order;
```

**Câu hỏi:** Vì sao chưa nên mặc định đây là một association hai hướng đúng chuẩn?

**Gợi ý:** Cả hai phía chưa được liên kết với `mappedBy`. Provider có thể hiểu chúng như các mapping association riêng, sinh cấu trúc liên kết hoặc cập nhật khác ý đồ. Với khóa ngoại `order_lines.order_id`, sửa thành `@OneToMany(mappedBy = "order")` ở `Order.lines` và giữ `@ManyToOne` ở `OrderLine.order`.

### Bài tập 5: Đăng ký khóa học có điểm số

`Student` có nhiều `Course`; mỗi `Course` có nhiều `Student`. Quan hệ còn có `enrolledAt`, `grade`.

**Câu hỏi:** Có nên dùng trực tiếp `@ManyToMany` hai hướng để lưu điểm?

**Gợi ý:** Thường nên tạo entity `Enrollment` chứa `student`, `course`, `enrolledAt` và `grade`. Có thể thêm collection `Student.enrollments` hoặc `Course.enrollments` ở những nơi use case cần điều hướng; không nhất thiết cả hai phía đều phải có collection.

### Bài tập 6: Tìm nguyên nhân không cập nhật khóa ngoại

Trong transaction:

```java
Author author = em.find(Author.class, 1L);
Book book = em.find(Book.class, 101L);

author.getBooks().add(book);
em.flush();
```

Mapping là `@OneToMany(mappedBy = "author")` ở `Author.books` và `@ManyToOne` ở `Book.author`.

**Câu hỏi:** Vì sao `books.author_id` có thể không thay đổi?

**Đáp án:** `Author.books` là inverse side. Chỉ thêm vào collection không đặt `book.author`; cần gọi helper cập nhật association ở owning side và đồng bộ object graph.

### Bài tập 7: Đánh giá hiệu năng

Trang danh sách chỉ cần `Author.name` và số lượng sách, nhưng code gọi `author.getBooks().size()` cho hàng trăm tác giả.

**Câu hỏi:** Nên đổi từ hai hướng sang đơn hướng ngay lập tức?

**Gợi ý:** Chưa chắc cần đổi mapping. Trước hết xem SQL thực tế và cân nhắc query aggregation/projection để lấy count theo tập hợp. Direction không quyết định hoàn toàn hiệu năng.

## 20. Quy trình thiết kế quan hệ trước khi viết annotation

Đối với một cặp entity có liên quan, có thể đi theo các câu hỏi:

1. **Cardinality là gì?** Một-một, một-nhiều, nhiều-một hay nhiều-nhiều?
2. **Use case cần điều hướng theo chiều nào?** Chỉ A → B, chỉ B → A hay cả hai?
3. **Schema sẽ lưu liên kết ở đâu?** Foreign key trên bảng nào, hay cần join table?
4. **Phía sở hữu mapping là phía nào?** Với hai hướng, phía đối ứng dùng `mappedBy` tới thuộc tính Java nào?
5. **Vòng đời của các entity liên quan ra sao?** Có cần `cascade` hoặc `orphanRemoval` không?
6. **Có cho phép ngắt liên kết không?** Foreign key có được phép `NULL`; nếu không thì hành vi gỡ quan hệ là chuyển chủ hay xóa entity?
7. **Object graph được giữ nhất quán thế nào?** Có helper `add/remove/set` cập nhật cả hai phía không?
8. **Use case cần tải dữ liệu bằng truy vấn nào?** Có nguy cơ N+1, collection lớn hoặc phân trang không?
9. **Dữ liệu ra API có cần dạng DTO không?** Tránh vô tình serialize vòng tham chiếu.
10. **Nếu đang đổi mapping cũ thì cần migration gì?** Kiểm tra join table, foreign key, constraint, index và dữ liệu lịch sử.

Một lựa chọn thiết kế tốt là lựa chọn **đủ đáp ứng nghiệp vụ và nhất quán với schema**, thay vì cố gắng thêm association ở cả hai class vì cảm giác “đầy đủ hơn”.

## 21. Tóm lược bằng một ví dụ xuyên suốt

Xét quan hệ `Book` và `Author`:

**Đơn hướng:**

```java
// Chỉ Book có association:
@ManyToOne
@JoinColumn(name = "author_id")
private Author author;
```

Đọc theo Java:

```text
Book → Author
```

Dữ liệu:

```text
books.author_id → authors.id
```

**Hai hướng:**

```java
// Book — owning side:
@ManyToOne
@JoinColumn(name = "author_id")
private Author author;

// Author — inverse side:
@OneToMany(mappedBy = "author")
private List<Book> books = new ArrayList<>();
```

Đọc theo Java:

```text
Book ↔ Author
```

Dữ liệu vẫn là:

```text
books.author_id → authors.id
```

**Khi chuyển tác giả của sách:**

```java
book.setAuthor(newAuthor);
```

với setter/helper cập nhật `oldAuthor.books`, `book.author` và `newAuthor.books` trong bộ nhớ. JPA đồng bộ liên kết thông qua **owning side** khi persistence context được flush trong transaction.

Cùng một khóa ngoại có thể hỗ trợ **hai hướng điều hướng trong Java**. Đó là sự khác biệt giữa cấu trúc dữ liệu quan hệ, hướng association trong object model và quyền sở hữu mapping JPA.

## Kết luận

**Quan hệ đơn hướng** có thuộc tính điều hướng từ một phía; **quan hệ hai hướng** cho phép đi từ cả hai phía trong object graph. Hai hướng không có nghĩa database phải lưu hai quan hệ khác nhau: khi mapping đúng, hai thuộc tính Java có thể chỉ tới **một foreign key hoặc một join table duy nhất**.

Với hai hướng, điều quan trọng là nhận diện **owning side** và **inverse side**. `@JoinColumn` hoặc `@JoinTable` mô tả cách lưu liên kết; `mappedBy` xác định phía đối ứng bằng tên thuộc tính Java. Việc thay đổi chỉ phía đối ứng không phải cách chuẩn để cập nhật liên kết trong database, và việc đổi chỉ owning side có thể khiến collection/tham chiếu trong bộ nhớ không nhất quán nếu không dùng helper method.

Khi chọn giữa đơn hướng và hai hướng, hãy dựa vào **nhu cầu điều hướng của nghiệp vụ, vòng đời entity, schema hiện hữu và cách truy vấn dữ liệu**. Hãy luôn tự hỏi: **“Ai cần đi tới ai trong Java, phía nào thực sự quản lý khóa ngoại, và một thao tác thay đổi quan hệ sẽ giữ cả object graph lẫn database nhất quán bằng cách nào?”**. Trả lời được ba câu hỏi này là nền tảng để thiết kế quan hệ JPA đúng và dễ bảo trì.
