# Ánh xạ hệ phân cấp bằng JOINED trong JPA

Trong lập trình hướng đối tượng, **kế thừa** cho phép nhiều lớp con dùng chung thuộc tính và hành vi của một lớp cha. Ví dụ, hệ thống xuất bản có lớp `Publication` đại diện cho ấn phẩm nói chung; hai lớp `Book` (sách) và `Magazine` (tạp chí) bổ sung những thông tin chỉ có ở từng loại.

Ở Java, quan hệ kế thừa dễ diễn đạt:

```java
public abstract class Publication {
    protected String title;
}

public class Book extends Publication {
    private String isbn;
}

public class Magazine extends Publication {
    private Integer issueNumber;
}
```

Nhưng cơ sở dữ liệu quan hệ không có khái niệm `extends` giống Java. Khi đưa các đối tượng trên vào database bằng **Jakarta Persistence (JPA)**, phải chọn một **chiến lược ánh xạ kế thừa** (*inheritance mapping strategy*) để biểu diễn các thuộc tính chung và riêng thành bảng/cột.

**`InheritanceType.JOINED`** là chiến lược trong đó:

- **Một bảng gốc** lưu khóa chính và các thuộc tính chung của hệ phân cấp.
- **Mỗi bảng lớp con** lưu các thuộc tính riêng của lớp con đó.
- **Khóa chính của hàng lớp con đồng thời là khóa ngoại** tham chiếu đến khóa chính của hàng gốc.
- Để dựng một đối tượng lớp con đầy đủ, JPA thường cần **kết hợp dữ liệu từ bảng gốc và bảng lớp con**, thông qua `JOIN` hoặc kế hoạch truy vấn tương đương.

Điểm nổi bật của JOINED là **giữ cấu trúc dữ liệu tương đối chuẩn hóa, tránh lặp lại các cột chung trong từng bảng lớp con**, đồng thời vẫn cho phép JPA truy vấn đa hình (*polymorphic queries*) trên lớp cha. Đổi lại, thao tác đọc/ghi có thể cần làm việc với nhiều bảng hơn.

Bài học này đi từ mô hình Java, SQL schema, annotation và vòng đời entity đến truy vấn đa hình, ràng buộc, hiệu năng, migration và những lỗi thường gặp khi triển khai JOINED.

## 1. Từ kế thừa Java sang hệ bảng quan hệ

Giả sử ứng dụng quản lý ba khái niệm:

- `Publication`: mọi ấn phẩm đều có `id`, `title`, `publisher`.
- `Book`: ngoài thông tin chung còn có `isbn` và `pageCount`.
- `Magazine`: ngoài thông tin chung còn có `issueNumber` và `issueDate`.

Sơ đồ lớp:

```text
                     Publication
                  -----------------
                  id : Long
                  title : String
                  publisher : String
                  version : Long
                         ^
                         |
            +------------+------------+
            |                         |
           Book                    Magazine
       -------------            -------------
       isbn : String            issueNumber : int
       pageCount : int          issueDate : LocalDate
```

Giả sử có dữ liệu:

```text
Book
  id          = 101
  title       = "Java nâng cao"
  publisher   = "Nhà xuất bản A"
  isbn        = "978-1-2345"
  pageCount   = 420

Magazine
  id          = 102
  title       = "Công nghệ tháng 6"
  publisher   = "Nhà xuất bản B"
  issueNumber = 6
  issueDate   = 2027-06-01
```

Với `JOINED`, dữ liệu được chia thành các bảng:

```text
publications
+-----+------------------+---------------+---------+
| id  | title            | publisher     | version |
+-----+------------------+---------------+---------+
| 101 | Java nâng cao    | Nhà xuất bản A|   0     |
| 102 | Công nghệ tháng 6| Nhà xuất bản B|   0     |
+-----+------------------+---------------+---------+
      ^                                   ^
      |                                   |
      | PK = FK                           | PK = FK
      |                                   |
books                                 magazines
+----------------+------------+-----------+
| publication_id | isbn       | page_count|
+----------------+------------+-----------+
| 101            | 978-1-2345 | 420       |
+----------------+------------+-----------+

magazines
+----------------+--------------+----------------+
| publication_id | issue_number | issue_date     |
+----------------+--------------+----------------+
| 102            | 6            | 2027-06-01     |
+----------------+--------------+----------------+
```

Đối với một `Book` có ID 101, JPA cần kết hợp:

1. Hàng `publications.id = 101` để lấy dữ liệu chung.
2. Hàng `books.publication_id = 101` để lấy dữ liệu chỉ thuộc `Book`.

**Không có hai định danh tách biệt** cho một cuốn sách. `Publication#101` và `Book#101` không phải hai entity độc lập cần tạo riêng; chúng là **một entity của kiểu thực tế `Book`**, có trạng thái được lưu trên hai bảng.

## 2. @Inheritance và InheritanceType.JOINED

JPA khai báo chiến lược kế thừa tại **entity gốc** của hệ phân cấp:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Inheritance;
import jakarta.persistence.InheritanceType;

@Entity
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Publication {
    // Các thuộc tính chung và @Id nằm ở đây.
}
```

Ý nghĩa của các thành phần:

| Thành phần | Vai trò |
| --- | --- |
| `@Entity` | Khai báo `Publication` là một entity thuộc mô hình persistence. |
| `@Inheritance` | Khai báo cách ánh xạ kế thừa entity trong hệ phân cấp. |
| `InheritanceType.JOINED` | Chọn cách dùng bảng gốc và các bảng lớp con nối theo khóa chính. |
| `abstract` | Không cho tạo trực tiếp `new Publication()` trong Java; **không ngăn** JPA truy vấn từ kiểu gốc. |
| `@Entity` trên `Book`, `Magazine` | Khai báo mỗi lớp con cụ thể là entity trong cùng hệ phân cấp. |
| `@Table` | Đặt tên bảng tương ứng với từng lớp entity. |
| `@PrimaryKeyJoinColumn` | Tùy chọn khai báo cột khóa chính của bảng lớp con tham chiếu khóa chính bảng cha. |

**Đặt `@Inheritance` ở gốc hệ phân cấp**, không rải các chiến lược khác nhau lên các lớp con của cùng một phân cấp rồi kỳ vọng JPA tự ghép chúng thành nhiều mô hình độc lập.

### 2.1. @Entity cha khác @MappedSuperclass

Một lớp cha được khai báo `@Entity` tạo ra một **kiểu entity có thể tham gia truy vấn đa hình**, và trong JOINED, nó có bảng gốc để lưu các thuộc tính chung.

Ngược lại:

```java
@MappedSuperclass
public abstract class Auditable {
    private java.time.Instant createdAt;
}
```

`@MappedSuperclass` chỉ cung cấp mapping cho lớp entity kế thừa. Nó **không trở thành entity riêng**, không có bảng riêng cho bản thân `Auditable` và không phải root đa hình trong JPQL như một `@Entity`.

Vì vậy, nếu mục đích là có **bảng gốc `publications`** và có thể viết `SELECT p FROM Publication p`, lớp `Publication` phải là `@Entity` dùng `JOINED`, không chỉ là `@MappedSuperclass`.

Một hệ thống có thể kết hợp cả hai: `Publication extends Auditable`, trong đó `Auditable` là mapped superclass chia sẻ timestamp, còn `Publication` là gốc entity JOINED. Các field inherited từ mapped superclass khi đó được ánh xạ vào bảng phù hợp theo mô hình entity.

## 3. Ví dụ hoàn chỉnh: lớp cha Publication

Ta dùng schema PostgreSQL minh họa với kiểu định danh `Long` sinh bằng identity column ở **bảng gốc**. Entity khai báo tương ứng:

```java
package com.example.library;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Inheritance;
import jakarta.persistence.InheritanceType;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "publications")
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Publication {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id")
    private Long id;

    @Column(name = "title", nullable = false, length = 200)
    private String title;

    @Column(name = "publisher", nullable = false, length = 120)
    private String publisher;

    @Version
    @Column(name = "version", nullable = false)
    private Long version;

    protected Publication() {
        // Constructor không tham số cho JPA.
    }

    protected Publication(String title, String publisher) {
        this.title = title;
        this.publisher = publisher;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getPublisher() {
        return publisher;
    }

    public Long getVersion() {
        return version;
    }

    public void rename(String title) {
        this.title = title;
    }
}
```

Các điểm cần nhớ:

- `@Id` và `@GeneratedValue` được khai báo **một lần ở entity gốc**. Các subclass **thừa hưởng định danh đó**.
- `@Version` ở entity gốc giúp tổ chức optimistic locking cho trạng thái của một entity trong hệ phân cấp. Nó không tạo một ID mới cho mỗi bảng.
- `Publication` là abstract, nhưng vẫn là `@Entity`. Có thể truy vấn `Publication` để nhận các instance `Book` hoặc `Magazine`.
- `@Inheritance(strategy = JOINED)` nằm tại root. Các lớp con được ánh xạ vào bảng riêng theo chiến lược này.
- Ví dụ chọn `IDENTITY` cho ID vì schema PostgreSQL ở phần sau minh họa cột identity. Trong dự án khác có thể chọn `SEQUENCE` hoặc `AUTO` nếu generator, schema và provider tương thích.

Cần phân biệt **trạng thái Java** và **hàng trong bảng**: một đối tượng `Book` chứa cả `title`, `publisher`, `isbn` và `pageCount` trong bộ nhớ, nhưng các giá trị này được ghi vào những bảng khác nhau.

## 4. Lớp con Book và khóa chính đồng thời là khóa ngoại

`Book` kế thừa các thuộc tính của `Publication` và thêm trường riêng:

```java
package com.example.library;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.PrimaryKeyJoinColumn;
import jakarta.persistence.Table;

@Entity
@Table(name = "books")
@PrimaryKeyJoinColumn(
    name = "publication_id",
    referencedColumnName = "id"
)
public class Book extends Publication {

    @Column(name = "isbn", nullable = false, length = 20)
    private String isbn;

    @Column(name = "page_count", nullable = false)
    private int pageCount;

    protected Book() {
    }

    public Book(
            String title,
            String publisher,
            String isbn,
            int pageCount) {
        super(title, publisher);
        this.isbn = isbn;
        this.pageCount = pageCount;
    }

    public String getIsbn() {
        return isbn;
    }

    public int getPageCount() {
        return pageCount;
    }

    public void changePageCount(int pageCount) {
        this.pageCount = pageCount;
    }
}
```

Ở đây:

- `@Entity` đánh dấu `Book` là một entity cụ thể.
- `@Table(name = "books")` chỉ định bảng riêng cho lớp con.
- `@PrimaryKeyJoinColumn(name = "publication_id", referencedColumnName = "id")` nói rằng **cột `books.publication_id` là khóa để nối đến `publications.id`**.
- `Book` **không khai báo thêm `@Id` hoặc `@GeneratedValue`**. Nó dùng ID inherited từ `Publication`.
- `title` và `publisher` không được khai báo lại ở `Book`; chúng đã được ánh xạ trong bảng gốc.

Trong mô hình `JOINED`, quan hệ giữa hai bảng có tính **một-một theo cùng định danh**. Không có chuyện một `Book` mang `books.id = 5` nhưng `publications.id = 101` theo một ID độc lập thứ hai. Giá trị khóa của cả hai hàng là 101.

### 4.1. Nếu không khai báo @PrimaryKeyJoinColumn thì sao?

`@PrimaryKeyJoinColumn` thường **không bắt buộc** nếu chấp nhận quy ước tên cột mặc định mà provider/JPA áp dụng cho subclass.

Ví dụ:

```java
@Entity
@Table(name = "books")
public class Book extends Publication {
    // Các thuộc tính riêng.
}
```

Trong một mapping đơn giản, cột nối khóa chính của subclass thường nhận tên tương ứng khóa chính bảng cha. Nếu schema đã có cột `publication_id` thay vì `id`, nên khai báo `@PrimaryKeyJoinColumn` tường minh để mapping khớp schema thực tế.

Với khóa chính gốc gồm nhiều thành phần, có thể cần `@PrimaryKeyJoinColumns` và đối chiếu đầy đủ các cột khóa ghép. Bài này dùng một `Long id` để làm rõ nguyên lý JOINED trước.

## 5. Lớp con Magazine

`Magazine` bổ sung một cấu trúc dữ liệu khác:

```java
package com.example.library;

import java.time.LocalDate;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.PrimaryKeyJoinColumn;
import jakarta.persistence.Table;

@Entity
@Table(name = "magazines")
@PrimaryKeyJoinColumn(
    name = "publication_id",
    referencedColumnName = "id"
)
public class Magazine extends Publication {

    @Column(name = "issue_number", nullable = false)
    private int issueNumber;

    @Column(name = "issue_date", nullable = false)
    private LocalDate issueDate;

    protected Magazine() {
    }

    public Magazine(
            String title,
            String publisher,
            int issueNumber,
            LocalDate issueDate) {
        super(title, publisher);
        this.issueNumber = issueNumber;
        this.issueDate = issueDate;
    }

    public int getIssueNumber() {
        return issueNumber;
    }

    public LocalDate getIssueDate() {
        return issueDate;
    }
}
```

Hai lớp `Book` và `Magazine` cùng dùng:

- **Bảng `publications`** cho `id`, `title`, `publisher`, `version`.
- **Bảng `books` hoặc `magazines` tương ứng** cho dữ liệu đặc thù.

Mã Java có thể sử dụng đa hình:

```java
Publication first = new Book(
    "Java nâng cao",
    "Nhà xuất bản A",
    "978-1-2345",
    420
);

Publication second = new Magazine(
    "Công nghệ tháng 6",
    "Nhà xuất bản B",
    6,
    java.time.LocalDate.of(2027, 6, 1)
);
```

Trong cả hai trường hợp, biến có kiểu `Publication` nhưng object thực có kiểu subclass cụ thể. JPA hỗ trợ đặc tính đó trong cả persistence context và JPQL.

## 6. Thiết kế các bảng JOINED trong SQL

Một schema PostgreSQL minh họa tương ứng với các annotation ở trên:

```sql
CREATE TABLE publications (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    publisher VARCHAR(120) NOT NULL,
    version BIGINT NOT NULL
);

CREATE TABLE books (
    publication_id BIGINT PRIMARY KEY,
    isbn VARCHAR(20) NOT NULL,
    page_count INTEGER NOT NULL,

    CONSTRAINT fk_books_publications
        FOREIGN KEY (publication_id)
        REFERENCES publications(id)
);

CREATE TABLE magazines (
    publication_id BIGINT PRIMARY KEY,
    issue_number INTEGER NOT NULL,
    issue_date DATE NOT NULL,

    CONSTRAINT fk_magazines_publications
        FOREIGN KEY (publication_id)
        REFERENCES publications(id)
);
```

Mỗi bảng subclass dùng **`publication_id` làm cả `PRIMARY KEY` và `FOREIGN KEY`**.

Ý nghĩa của hai constraint:

1. `PRIMARY KEY(publication_id)` ở bảng con: không thể có hai hàng `books` cùng chỉ tới một hàng gốc.
2. `FOREIGN KEY(publication_id) REFERENCES publications(id)`: một hàng `books` không thể tồn tại nếu thiếu hàng `publications` tương ứng.

Tương tự đối với `magazines`.

Tạo dữ liệu tương ứng một cuốn sách:

```sql
INSERT INTO publications (id, title, publisher, version)
OVERRIDING SYSTEM VALUE
VALUES (101, 'Java nâng cao', 'Nhà xuất bản A', 0);

INSERT INTO books (publication_id, isbn, page_count)
VALUES (101, '978-1-2345', 420);
```

`OVERRIDING SYSTEM VALUE` ở đây chỉ minh họa khả năng cấp ID tường minh trong PostgreSQL; với cột `GENERATED BY DEFAULT AS IDENTITY`, việc chèn một ID tường minh thường không cần cú pháp này, và nếu dùng dữ liệu tạo tay thì còn phải căn chỉnh identity sequence. Trong ứng dụng JPA, **không nên tự chạy các lệnh chèn này cho mỗi entity**; `persist(book)` sẽ điều phối việc lưu cả bảng gốc và bảng con.

Trong database thực tế, nếu ID có thứ tự cấp phát tự động, có thể minh họa logic nghiệp vụ bằng:

```sql
-- Ý tưởng: chèn publications để lấy ID vừa cấp,
-- rồi chèn books với đúng ID đó trong cùng transaction.
-- Cách lấy ID phụ thuộc DBMS/driver/provider.
```

### 6.1. Không phải có hai khóa chính độc lập

Một sai lầm là thiết kế:

```sql
CREATE TABLE books (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    publication_id BIGINT REFERENCES publications(id),
    isbn VARCHAR(20) NOT NULL
);
```

Cách này tạo **hai giá trị định danh**: `books.id` và `books.publication_id`. Nó giống thiết kế hai entity có quan hệ, **không phải cách JOINED chuẩn đang dùng với một identity inherited**.

Với JOINED, một hàng subclass được định danh bằng **cùng giá trị khóa** với hàng của superclass. Nếu tên cột khác nhau thì **giá trị vẫn giống nhau** và quan hệ khóa chính/khóa ngoại phải phản ánh điều đó.

### 6.2. Các cột riêng được phép NOT NULL

Ở chiến lược `SINGLE_TABLE`, các field riêng của subtype có thể cần `NULL` trên hàng thuộc subtype khác vì mọi loại entity cùng một bảng. JOINED tách field riêng sang bảng subclass; do đó có thể khai báo:

```sql
books.isbn VARCHAR(20) NOT NULL
magazines.issue_number INTEGER NOT NULL
```

Một `Magazine` không có hàng trong `books` nên không bị buộc phải có `isbn`. Đây là ưu điểm của JOINED về **ràng buộc nullability cho thuộc tính đặc thù**.

### 6.3. Ràng buộc nào chưa được ba bảng tự đảm bảo?

PK/FK trên `books` và `magazines` đảm bảo **bảng con có bảng gốc** và mỗi bảng con không có hai hàng cùng ID. Tuy nhiên, **chỉ với những ràng buộc đó**:

- Database vẫn có thể chứa một hàng `publications` nhưng chưa có hàng trong bất kỳ bảng con nào.
- Một ID về mặt SQL có thể xuất hiện đồng thời trong `books` và `magazines` nếu không có biện pháp bổ sung ngăn điều đó.

Nếu `Publication` là abstract, hai trạng thái trên **không phải hình dạng entity hợp lệ mà ứng dụng mong muốn**. JPA provider thông thường kiểm soát tính nhất quán khi chính nó persist entity, nhưng các writer ngoài JPA, migration hoặc SQL thủ công vẫn có thể phá vỡ invariant.

Nếu hệ thống phải bảo vệ tuyệt đối tính độc quyền subtype tại tầng database, cần thiết kế thêm **discriminator, trigger hoặc quy tắc dữ liệu phù hợp**. Một cột discriminator đơn thuần chưa tự động tạo constraint liên bảng đảm bảo chỉ có đúng một hàng subtype; mức bảo vệ phải được thiết kế và kiểm chứng cụ thể.

## 7. Persist một subclass diễn ra thế nào?

Giả sử `EntityManager` nằm trong transaction và có một `Book` mới:

```java
Book book = new Book(
    "Java nâng cao",
    "Nhà xuất bản A",
    "978-1-2345",
    420
);

entityManager.persist(book);
```

Về mặt logic, JPA cần lưu:

```text
1. INSERT bảng gốc publications
       title      = "Java nâng cao"
       publisher  = "Nhà xuất bản A"
       id         = ID được cấp
       version    = giá trị version ban đầu

2. INSERT bảng con books
       publication_id = cùng ID
       isbn           = "978-1-2345"
       page_count     = 420
```

Ví dụ SQL tương đương:

```sql
INSERT INTO publications (title, publisher, version)
VALUES (?, ?, ?);

-- Sau khi có ID của publication:
INSERT INTO books (publication_id, isbn, page_count)
VALUES (?, ?, ?);
```

SQL ở trên chỉ minh họa. Provider có thể dùng `RETURNING`, JDBC generated keys, sequence hoặc các cơ chế khác để nhận định danh; thứ tự và thời điểm chạy SQL tùy chiến lược sinh khóa và flush.

Điều quan trọng là **cả hai thao tác lưu thuộc cùng một transaction thích hợp**. Nếu ghi thành công hàng gốc nhưng việc ghi hàng con thất bại, transaction nên rollback để tránh để lại dữ liệu phân cấp không nhất quán.

### 7.1. Ví dụ sử dụng EntityManager với RESOURCE_LOCAL

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;

public final class PublicationWriter {
    private final EntityManagerFactory factory;

    public PublicationWriter(EntityManagerFactory factory) {
        this.factory = factory;
    }

    public Long createBook() {
        EntityManager em = factory.createEntityManager();
        try {
            EntityTransaction tx = em.getTransaction();

            try {
                tx.begin();

                Book book = new Book(
                    "Java nâng cao",
                    "Nhà xuất bản A",
                    "978-1-2345",
                    420
                );

                em.persist(book);
                tx.commit();

                return book.getId();
            } catch (RuntimeException ex) {
                if (tx.isActive()) {
                    tx.rollback();
                }
                throw ex;
            }
        } finally {
            em.close();
        }
    }
}
```

Ví dụ giả định đã có `EntityManagerFactory` cấu hình persistence unit kiểu `RESOURCE_LOCAL` và đã đăng ký các entity. Với Jakarta EE/JTA hoặc Spring `@Transactional`, framework quản lý transaction thay vì gọi `EntityTransaction` thủ công.

**Không gọi `persist` riêng với một object `Publication` khác để “tạo hàng gốc”.** JPA nhận một instance `Book`, xác định loại thực tế và tự quản lý việc ghi các bảng trong hệ phân cấp.

### 7.2. Một ID cho toàn bộ đối tượng

Sau khi lưu thành công:

```java
Long id = book.getId();
```

ID đó dùng được để tìm object theo kiểu `Book` hoặc theo kiểu gốc `Publication`:

```java
Book bookAgain = entityManager.find(Book.class, id);
Publication publicationAgain =
    entityManager.find(Publication.class, id);
```

Nếu ID thực sự thuộc `Book`, cả hai lời gọi có thể đại diện cùng một entity được quản lý, nhưng kiểu khai báo của biến thứ hai là `Publication`. Theo đặc tính identity map, một persistence context không nên duy trì hai managed entity độc lập cho cùng danh tính entity trong hệ phân cấp.

Không thể lấy một `Magazine` chỉ nhờ biết ID của `Book`:

```java
Magazine magazine = entityManager.find(Magazine.class, id);
// Nếu ID không thuộc Magazine, kết quả không phải Magazine phù hợp.
```

Đừng dựa vào hành vi của provider khi cố ép một ID sang sai kiểu subtype; hãy truy vấn đúng kiểu và kiểm tra kết quả hợp lệ.

## 8. Truy vấn đa hình với JOINED

Một ưu điểm chính của entity inheritance là **polymorphism**: có thể yêu cầu dữ liệu ở kiểu gốc và nhận về các subclass thực tế.

### 8.1. Tìm theo kiểu gốc Publication

```java
List<Publication> publications = entityManager.createQuery(
        "SELECT p FROM Publication p ORDER BY p.title",
        Publication.class
    )
    .getResultList();
```

Danh sách có thể chứa cả `Book` và `Magazine`:

```java
for (Publication publication : publications) {
    System.out.println(publication.getTitle());

    if (publication instanceof Book book) {
        System.out.println("ISBN: " + book.getIsbn());
    } else if (publication instanceof Magazine magazine) {
        System.out.println(
            "Số phát hành: " + magazine.getIssueNumber()
        );
    }
}
```

Cú pháp pattern matching `instanceof` ở ví dụ yêu cầu phiên bản Java có hỗ trợ. Nếu dự án dùng Java cũ hơn, có thể dùng `instanceof` và ép kiểu truyền thống.

Provider phải tìm cách xác định **loại entity thực tế** của từng hàng, thường nhờ discriminator (nếu có) hoặc việc kết hợp dữ liệu các bảng subclass. Vì vậy, truy vấn root có thể tốn chi phí hơn một câu `SELECT` từ bảng `publications` đơn lẻ.

### 8.2. SQL JOIN minh họa

Một cách SQL có thể biểu diễn truy vấn trên root:

```sql
SELECT
    p.id,
    p.title,
    p.publisher,
    p.version,
    b.isbn,
    b.page_count,
    m.issue_number,
    m.issue_date
FROM publications p
LEFT JOIN books b
    ON b.publication_id = p.id
LEFT JOIN magazines m
    ON m.publication_id = p.id
ORDER BY p.title;
```

Nhờ `LEFT JOIN`, một hàng `Publication` thuộc `Book` vẫn xuất hiện dù không có hàng `Magazine` cùng ID, và ngược lại.

**Đây là SQL để giải thích nguyên lý, không phải SQL JPA provider bắt buộc phải phát ra.** Provider có thể dùng discriminator, một số truy vấn bổ sung, tối ưu theo subtype, cache, kế hoạch fetch hay cú pháp dialect khác.

Đặc biệt khi hệ phân cấp có **nhiều subclass**, truy vấn đa hình từ root có thể phải kết hợp nhiều bảng hoặc nhiều nguồn dữ liệu; điều đó cần được xét khi thiết kế chức năng đọc số lượng lớn.

### 8.3. Truy vấn trực tiếp Book

Nếu ứng dụng chỉ cần sách, nên truy vấn trực tiếp subtype:

```java
List<Book> books = entityManager.createQuery(
        "SELECT b FROM Book b WHERE b.pageCount >= :pages",
        Book.class
    )
    .setParameter("pages", 300)
    .getResultList();
```

SQL ý tưởng:

```sql
SELECT
    p.id,
    p.title,
    p.publisher,
    p.version,
    b.isbn,
    b.page_count
FROM books b
JOIN publications p
    ON p.id = b.publication_id
WHERE b.page_count >= ?;
```

Truy vấn subtype vẫn cần dữ liệu bảng gốc cho các thuộc tính chung nhưng có thể tránh xử lý những bảng subclass không liên quan.

### 8.4. TYPE và TREAT trong JPQL

JPA hỗ trợ các biểu thức liên quan đến polymorphic type.

Dùng `TYPE` để chọn một loại entity:

```java
List<Publication> onlyBooks = entityManager.createQuery(
        "SELECT p FROM Publication p WHERE TYPE(p) = Book",
        Publication.class
    )
    .getResultList();
```

`Book` ở đây là tên entity trong JPQL theo mapping JPA, không phải chuỗi SQL literal hay tên bảng `books`. Trong ứng dụng có khai báo `@Entity(name = "...")`, tên entity JPQL phải dùng tên đã cấu hình.

Dùng `TREAT` để truy cập field chỉ tồn tại trên subclass:

```java
List<Publication> matches = entityManager.createQuery(
        "SELECT p FROM Publication p " +
        "WHERE TREAT(p AS Book).isbn = :isbn",
        Publication.class
    )
    .setParameter("isbn", "978-1-2345")
    .getResultList();
```

`TREAT` cho phép diễn đạt thao tác chuyển kiểu trong JPQL khi đang truy vấn qua root. Nếu use case chỉ làm việc với `Book`, truy vấn trực tiếp `Book` thường dễ đọc hơn:

```java
Book match = entityManager.createQuery(
        "SELECT b FROM Book b WHERE b.isbn = :isbn",
        Book.class
    )
    .setParameter("isbn", "978-1-2345")
    .getResultStream()
    .findFirst()
    .orElse(null);
```

Nếu ISBN cần duy nhất, đặt constraint `UNIQUE` ở bảng `books` và xử lý trường hợp không tìm thấy rõ ràng. Không nên dựa vào `findFirst()` để che dữ liệu trùng khi schema đáng lẽ chỉ cho một kết quả.

## 9. Discriminator trong chiến lược JOINED

**Discriminator** là một giá trị dùng để chỉ ra subtype của một hàng gốc, ví dụ `"BOOK"` hoặc `"MAGAZINE"`. Trong chiến lược `SINGLE_TABLE`, discriminator thường đặc biệt quan trọng vì mọi subtype dùng chung một bảng. Với `JOINED`, một số provider có thể nhận diện subtype từ các bảng subclass nên **không nhất thiết phải có cột discriminator tường minh**.

Nếu muốn khai báo một discriminator có chủ đích, có thể cấu hình thêm:

```java
@Entity
@Table(name = "publications")
@Inheritance(strategy = InheritanceType.JOINED)
@DiscriminatorColumn(
    name = "publication_type",
    discriminatorType = DiscriminatorType.STRING,
    length = 20
)
public abstract class Publication {
    // @Id, các thuộc tính chung...
}
```

Các subclass:

```java
@Entity
@DiscriminatorValue("BOOK")
@Table(name = "books")
public class Book extends Publication {
    // ...
}

@Entity
@DiscriminatorValue("MAGAZINE")
@Table(name = "magazines")
public class Magazine extends Publication {
    // ...
}
```

Các ví dụ này **minh họa annotation bổ sung** cho mô hình ở trên, không phải khai báo thêm các lớp trùng tên trong cùng dự án. Khi chọn discriminator, schema bảng gốc cần có cột `publication_type` phù hợp và dữ liệu legacy cần được xử lý.

Một số điểm cần hiểu:

- `@DiscriminatorColumn` khai báo cột nhận diện subtype; nó **không thay thế** khóa chính/khóa ngoại nối bảng trong JOINED.
- `@DiscriminatorValue` xác định giá trị dùng cho một subclass nếu có cơ chế discriminator tương ứng.
- Tác dụng cụ thể của discriminator đối với chiến lược JOINED, nhất là khi không khai báo rõ, có thể chịu ảnh hưởng provider và phiên bản; cần quan sát schema/SQL thực tế.
- Discriminator không tự động tạo ràng buộc xuyên bảng bảo đảm rằng một `publication_type = 'BOOK'` luôn có đúng một hàng trong `books` và không có hàng trong `magazines`. Nếu cần bảo đảm tuyệt đối khi có writer ngoài JPA, phải thiết kế constraint/trigger và quy trình ghi tương ứng.

**Không nên coi discriminator là cách đổi từ JOINED về SINGLE_TABLE.** Dù có discriminator, dữ liệu riêng của `Book` vẫn nằm trong `books` và dữ liệu riêng của `Magazine` vẫn nằm trong `magazines`.

## 10. Thêm nhiều tầng kế thừa

JOINED không chỉ giới hạn một lớp cha và hai subclass trực tiếp. Một hệ phân cấp có thể có nhiều tầng:

```text
             Publication
                  |
          PrintedPublication
                  |
                 Book
```

Ví dụ:

- `Publication`: `id`, `title`.
- `PrintedPublication`: `printEdition`.
- `Book`: `isbn`.

Nếu **cả ba đều là `@Entity` trong một hệ JOINED**, mô hình bảng thường tương ứng:

```text
publications
    id (PK)
    title

printed_publications
    publication_id (PK, FK -> publications.id)
    print_edition

books
    publication_id (PK, FK -> printed_publications.publication_id)
    isbn
```

Một `Book` khi đó có dữ liệu trải trên **ba bảng**. Để dựng Book đầy đủ, provider cần phối hợp những bảng tương ứng trong hệ phân cấp.

Một đoạn khai báo lớp trung gian:

```java
@Entity
@Table(name = "printed_publications")
@PrimaryKeyJoinColumn(name = "publication_id")
public abstract class PrintedPublication extends Publication {
    private Integer printEdition;

    protected PrintedPublication() {
    }

    protected PrintedPublication(
            String title,
            String publisher,
            Integer printEdition) {
        super(title, publisher);
        this.printEdition = printEdition;
    }
}
```

Nếu `Book` kế thừa từ `PrintedPublication` thay vì trực tiếp từ `Publication`, schema và constructor của `Book` phải được điều chỉnh tương ứng. Đây là **một biến thể riêng**, không sử dụng đồng thời với các class `Book extends Publication` ở ví dụ trước.

### 10.1. Một lớp trung gian @MappedSuperclass thì khác

Nếu `PrintedPublication` là `@MappedSuperclass` thay vì `@Entity`, nó không có bảng riêng. Những thuộc tính được khai báo ở mapped superclass sẽ được ánh xạ vào các bảng entity phù hợp trong hệ phân cấp. Vì vậy, đổi một lớp từ `@Entity` sang `@MappedSuperclass` có thể **thay đổi số bảng và nơi chứa cột**, chứ không chỉ đổi một annotation về mặt Java.

### 10.2. Chiều sâu của cây kế thừa ảnh hưởng SQL

Trong một chuỗi kế thừa JOINED sâu:

```text
Root -> Level1 -> Level2 -> ConcreteLeaf
```

entity ở tầng cuối có thể cần dữ liệu từ nhiều bảng liên tiếp. Nếu hệ phân cấp sâu và có nhiều nhánh, các truy vấn đa hình hoặc cập nhật có thể phức tạp hơn.

Vì thế không nên dùng kế thừa nhiều tầng chỉ để tái sử dụng vài field chung. Với các giá trị chia sẻ không cần identity polymorphic, cân nhắc `@Embeddable` hoặc `@MappedSuperclass` nếu phù hợp domain.

## 11. Quan hệ tới kiểu gốc và truy vấn đa hình

Một entity khác có thể giữ liên kết đến `Publication` thay vì một subclass cụ thể.

Ví dụ bảng `reading_list_items` lưu danh sách ấn phẩm mà người dùng muốn đọc:

```sql
CREATE TABLE reading_list_items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    publication_id BIGINT NOT NULL,
    CONSTRAINT fk_reading_list_publication
        FOREIGN KEY (publication_id)
        REFERENCES publications(id)
);
```

Entity:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "reading_list_items")
public class ReadingListItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "publication_id", nullable = false)
    private Publication publication;

    protected ReadingListItem() {
    }

    public Publication getPublication() {
        return publication;
    }
}
```

Khóa ngoại `reading_list_items.publication_id` tham chiếu **bảng gốc `publications`**. Định danh này có thể thuộc một `Book` hoặc `Magazine`.

Khi truy cập:

```java
Publication publication = item.getPublication();
```

provider cần biểu diễn association theo kiểu khai báo `Publication`, đồng thời nhận diện subtype thực tế khi cần. Với một mapping LAZY, việc nhận diện subclass hoặc lấy dữ liệu lớp con có thể đòi hỏi truy vấn bổ sung tùy provider, proxy và cách thực thi.

Trong mô hình này, `ReadingListItem` không cần hai cột foreign key riêng `book_id` và `magazine_id`. Một khóa ngoại đến bảng gốc hỗ trợ **quan hệ đa hình đến toàn bộ hệ phân cấp**.

### 11.1. Nếu quan hệ chỉ chấp nhận Book?

Nếu một association chỉ hợp lệ với sách, trường có thể được khai báo:

```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "book_id")
private Book book;
```

Cột khóa ngoại cần được thiết kế phù hợp với **bảng/khóa của Book** theo mapping JOINED. Tùy mô hình, có thể tham chiếu `books.publication_id` thay vì chỉ dựa vào bảng gốc để bảo vệ điều kiện “đây thực sự là Book” ở tầng database.

Nhưng không nên tự suy diễn tên cột và target constraint trong mọi schema; phải kiểm tra DDL JPA/provider và tạo migration nhất quán.

### 11.2. Cascade không phụ thuộc chiến lược inheritance

Nếu `ReadingListItem` có quan hệ đến `Publication`, việc có `JOINED` **không tự bật cascade PERSIST/MERGE/REMOVE**. Cascade là một lựa chọn trên association, khác với chiến lược lưu các bảng của một entity.

Ví dụ:

```java
@ManyToOne(fetch = FetchType.LAZY)
private Publication publication;
```

mặc định không cascade thao tác. Xóa một mục danh sách đọc thông thường **không được xóa luôn Book hoặc Magazine** được nhiều người dùng tham chiếu. Không nên đặt `CascadeType.REMOVE` chỉ vì nghĩ hàng `books` phụ thuộc hàng `publications` theo JOINED: đó là quan hệ giữa **các bảng lưu cùng một entity**, không phải quan hệ sở hữu giữa hai entity nghiệp vụ tách biệt.

## 12. UPDATE và DELETE trong JOINED

### 12.1. Cập nhật thuộc tính chung

Giả sử:

```java
Book book = entityManager.find(Book.class, bookId);
book.rename("Java nâng cao - tái bản");
```

`title` là thuộc tính khai báo ở `Publication` và ánh xạ vào bảng `publications`. Khi flush, provider có thể tạo câu lệnh tương tự:

```sql
UPDATE publications
SET title = ?,
    version = ?
WHERE id = ?
  AND version = ?;
```

Chi tiết optimistic locking phụ thuộc provider, nhưng **trường title không nằm trong bảng `books`**.

### 12.2. Cập nhật thuộc tính riêng

```java
Book book = entityManager.find(Book.class, bookId);
book.changePageCount(450);
```

`pageCount` nằm trong bảng `books`. Provider cần đồng bộ cột `books.page_count`, đồng thời xử lý version theo mô hình optimistic locking đang được áp dụng.

SQL có thể có dạng:

```sql
UPDATE books
SET page_count = ?
WHERE publication_id = ?;
```

Với `@Version` đặt ở root, provider có thể cần thêm thao tác đối với bảng gốc để kiểm tra/tăng version; không nên mặc định rằng một thay đổi chỉ ở subtype luôn tạo đúng **một** câu SQL UPDATE.

### 12.3. Xóa một Book

```java
Book book = entityManager.find(Book.class, bookId);
entityManager.remove(book);
```

JPA phải loại bỏ trạng thái entity khỏi **các bảng** tương ứng. Một luồng SQL có thể là:

```sql
DELETE FROM books
WHERE publication_id = ?;

DELETE FROM publications
WHERE id = ?;
```

Thứ tự và số lệnh thực tế phụ thuộc schema, foreign key, provider và giao dịch. Nếu database có `ON DELETE CASCADE`, hành vi thực thi SQL có thể khác, nhưng phải giữ persistence context và cache nhất quán.

**Không xóa riêng hàng `books` rồi giữ `publications` lại** nếu mục tiêu là xóa entity Book hoàn toàn. Hai hàng cùng cấu thành một entity.

### 12.4. Quan hệ và vòng đời không giống nhau

Trong `JOINED`, việc tồn tại hai bảng không có nghĩa có hai entity để áp dụng `CascadeType.REMOVE`. `Book` và phần `Publication` inherited là **một entity**, nên thao tác remove Book xử lý các bảng của nó theo inheritance mapping.

Ngược lại, nếu `Book` có `@OneToMany List<Review>`, các `Review` là entity khác; xóa review theo Book cần cascade/orphanRemoval hoặc nghiệp vụ riêng.

## 13. Optimistic locking và @Version trong hệ JOINED

Khi nhiều giao dịch cùng sửa một entity, `@Version` có thể phát hiện cập nhật dựa trên trạng thái cũ:

```java
@Version
@Column(name = "version", nullable = false)
private Long version;
```

Đặt version trong `Publication` giúp cả `Book` và `Magazine` thừa hưởng cơ chế định phiên bản.

Ví dụ tình huống:

```text
Transaction A                       Transaction B
    |                                   |
Đọc Book#101, version=0             Đọc Book#101, version=0
    |                                   |
Đổi title                           Đổi pageCount
    |                                   |
Commit thành công                   Commit trên version cũ
version -> 1                        -> Có thể bị optimistic locking conflict
```

Vì cùng một `Book` là entity có ID 101 và version chung trong mô hình JPA, thay đổi trường gốc và trường subclass đều liên quan đến trạng thái của **cùng entity**.

Provider có thể dùng một hoặc nhiều câu SQL để kiểm tra và tăng version; API thường thông báo xung đột bằng `OptimisticLockException` hoặc ngoại lệ transaction tương ứng. Các chi tiết SQL không nên được hardcode thành giả định nghiệp vụ.

**Không khai báo một `@Version` độc lập ở mỗi subclass** như thể mỗi bảng có cơ chế version tách biệt cho cùng một entity. Khi dùng version mapping, nên tổ chức một cách nhất quán cho hệ phân cấp, thường là tại root.

Nếu nghiệp vụ có nhiều giao dịch cùng sửa những bản ghi liên quan, ví dụ một `ReadingListItem` và `Book`, version của `Book` **không tự giải quyết tất cả concurrency bên ngoài entity đó**. Cần xét transaction và locking theo phạm vi invariant thực tế.

## 14. JOINED và hiệu năng truy vấn

JOINED có ưu điểm chuẩn hóa dữ liệu, nhưng chi phí truy vấn đáng chú ý ở ba trường hợp.

### 14.1. Truy vấn một subclass cần dữ liệu từ nhiều bảng

Để tạo đối tượng `Book` với cả `title` và `isbn`, provider thường phải kết hợp `publications` và `books`. Database cần xử lý join trên các khóa.

Vì hai bên nối theo PK/FK đã có index/constraint phù hợp, việc join một cuốn sách theo ID thường khá tự nhiên đối với optimizer. Tuy nhiên, chi phí thực tế còn phụ thuộc kích thước bảng, chỉ số, số subtype, tải hệ thống và kế hoạch thực thi.

### 14.2. Truy vấn từ root có thể liên quan nhiều subclass

`SELECT p FROM Publication p` là truy vấn đa hình. Nếu hệ có 20 subtype, provider có thể cần tạo một kế hoạch đọc phức tạp hơn so với chỉ lấy một bảng đơn.

Nếu màn hình chỉ cần `title` và `publisher` của 1.000 ấn phẩm, việc tải **toàn bộ entity** có thể khiến provider xử lý cả thông tin nhận diện subtype và các trường không cần hiển thị. Trong một số use case, **projection** chỉ lấy dữ liệu cần thiết có thể hiệu quả hơn.

Ví dụ JPQL scalar projection:

```java
List<Object[]> rows = entityManager.createQuery(
        "SELECT p.id, p.title FROM Publication p",
        Object[].class
    )
    .getResultList();

for (Object[] row : rows) {
    Long id = (Long) row[0];
    String title = (String) row[1];
    System.out.println(id + ": " + title);
}
```

Đây chỉ là ví dụ truy vấn dữ liệu tối thiểu, không phải cam kết rằng provider chắc chắn không tham chiếu bảng subclass trong mọi kế hoạch SQL.

Với Java hiện đại, có thể dùng DTO projection để tránh `Object[]` ở tầng ứng dụng nếu cần API type-safe hơn.

### 14.3. Truy vấn kết hợp quan hệ có thể phức tạp thêm

Nếu `Book` còn có `@OneToMany List<Review>`, một truy vấn lấy cả Book, Publication fields và reviews có thể kết hợp:

- JOIN bảng root.
- JOIN bảng subclass.
- JOIN bảng quan hệ review hoặc các truy vấn bổ sung để tải collection.

Vấn đề **N+1**, eager fetching, fetch join và phân trang vẫn tồn tại như với entity bình thường; JOINED có thể làm kế hoạch truy vấn có thêm các bảng kế thừa.

Không nên mặc định bật `FetchType.EAGER` cho mọi association chỉ vì muốn giảm số lần JOIN ở inheritance. **Inheritance JOIN** và **association fetching** là hai khía cạnh khác nhau.

### 14.4. INSERT, UPDATE và DELETE cũng có chi phí nhiều bảng

Một Book mới thường cần ít nhất:

1. Ghi hàng gốc.
2. Ghi hàng subclass.

Xóa Book cũng cần xử lý cả hai bảng, còn cập nhật thuộc tính chung/riêng có thể ảnh hưởng một hoặc nhiều bảng tùy version và provider.

Với một hệ thống ghi rất nhiều entity mỗi giây, số lượng bảng phải thao tác có thể là yếu tố quan trọng. Chiến lược sinh khóa cũng ảnh hưởng batching: `GenerationType.IDENTITY` có thể đòi hỏi lấy ID từ INSERT bảng gốc, trong khi `SEQUENCE` có thể cho phép cấp ID trước để tối ưu một số thao tác, tùy DBMS và provider.

**Không nên kết luận JOINED luôn chậm**. Khi dữ liệu có nhiều field chỉ thuộc một số subtype, việc tách bảng cũng có thể giảm số cột không liên quan và cho phép index/ràng buộc riêng hiệu quả. Quyết định nên dựa vào workload thực tế và quan sát SQL/kế hoạch truy vấn.

## 15. Index và constraint trong JOINED

Các constraint quan trọng:

- `PRIMARY KEY(publications.id)`.
- `PRIMARY KEY(books.publication_id)`, đồng thời là FK tới root.
- `PRIMARY KEY(magazines.publication_id)`, đồng thời là FK tới root.
- `NOT NULL` cho field bắt buộc của từng subtype.
- `UNIQUE` trên các giá trị cần duy nhất theo domain.

Ví dụ ISBN duy nhất giữa các sách:

```sql
ALTER TABLE books
ADD CONSTRAINT uq_books_isbn UNIQUE (isbn);
```

Chỉ mục phục vụ truy vấn thường xuyên theo ISBN có thể được database tạo qua unique constraint. Với tìm tạp chí theo số phát hành và ngày:

```sql
CREATE INDEX idx_magazines_issue
ON magazines(issue_number, issue_date);
```

Không nên thêm index tràn lan: chi phí ghi và dung lượng lưu trữ cũng tăng theo số index.

### 15.1. Unique trên thuộc tính chung

Nếu `Publication` có một mã dùng chung cho mọi loại ấn phẩm, ví dụ `globalCode`, lưu thuộc tính này ở bảng root giúp đặt `UNIQUE` **trên một bảng**, áp dụng cho cả Book lẫn Magazine.

Nếu mỗi subclass giữ mã ở bảng riêng, một unique constraint trong `books` không bảo vệ dữ liệu `magazines`. Đây là quyết định đặt trường chung/riêng cần cân nhắc ngay từ mô hình domain.

### 15.2. Constraint xuyên subtype không tự có

Giả sử mỗi `Book` chỉ được tồn tại một hàng subclass, PK đã đáp ứng. Nhưng ràng buộc “một root ID chỉ thuộc đúng một trong hai bảng books hoặc magazines” **không được FK/PK đơn giản tự thực hiện**.

Nếu dữ liệu chỉ được ghi qua JPA provider và không có lỗi mapping, provider xử lý loại entity theo runtime class. Nếu có những writer SQL khác, nên có quy tắc và kiểm soát thích hợp để tránh:

```text
publications.id = 101
books.publication_id = 101
magazines.publication_id = 101   <-- cùng root ID xuất hiện ở hai loại
```

Không được coi một ràng buộc `CHECK(publication_type IN (...))` trên bảng gốc là đủ để ngăn dữ liệu bất nhất giữa hai bảng con; đó là kiểm tra giá trị trong một bảng, chưa bảo vệ toàn bộ quan hệ xuyên bảng.

## 16. So sánh JOINED với SINGLE_TABLE và TABLE_PER_CLASS

JPA có ba chiến lược entity inheritance thường gặp:

| Chiến lược | Cách lưu các thuộc tính | Ưu điểm nổi bật | Hạn chế nổi bật |
| --- | --- | --- | --- |
| `SINGLE_TABLE` | Toàn bộ hệ phân cấp trong **một bảng**; cột chung và cột riêng nằm cạnh nhau. | Truy vấn đa hình có thể đơn giản, tránh JOIN giữa các bảng inheritance. | Nhiều cột không áp dụng cho subtype này phải để NULL; schema dễ rộng, constraint theo subtype phức tạp. |
| **`JOINED`** | Bảng gốc chứa field chung; mỗi subclass có bảng riêng chứa field riêng; nối bằng PK/FK. | Tương đối chuẩn hóa, tránh lặp cột chung, dễ đặt `NOT NULL` cho field riêng. | Tải subclass và truy vấn đa hình thường phải phối hợp nhiều bảng; ghi/xóa có thể nhiều SQL. |
| `TABLE_PER_CLASS` | Mỗi concrete entity có bảng chứa cả trường inherited và trường riêng. | Truy vấn concrete subtype có thể dùng bảng riêng, không cần inheritance join. | Các trường chung lặp ở nhiều bảng; truy vấn root có thể cần union; quản lý ID/schema phức tạp hơn. |

Ví dụ với `Publication`, `Book`, `Magazine`:

**SINGLE_TABLE:**

```text
publications(
  id, publication_type, title, publisher,
  isbn, page_count, issue_number, issue_date
)
```

**JOINED:**

```text
publications(id, title, publisher)
books(publication_id, isbn, page_count)
magazines(publication_id, issue_number, issue_date)
```

**TABLE_PER_CLASS:**

```text
books(id, title, publisher, isbn, page_count)
magazines(id, title, publisher, issue_number, issue_date)
```

Ba chiến lược hướng tới cùng một ý tưởng OO inheritance nhưng đánh đổi khác nhau về schema và SQL. Không có chiến lược nào luôn đúng trong mọi dự án.

### 16.1. Khi JOINED thường phù hợp

JOINED đáng cân nhắc khi:

- Nhiều subclass **thực sự có quan hệ is-a** với root và cần truy vấn đa hình.
- Các thuộc tính chung tương đối ổn định, có ý nghĩa giống nhau trên mọi subtype.
- Mỗi subtype có nhiều trường riêng cần `NOT NULL` hoặc ràng buộc riêng.
- Không muốn lặp lại toàn bộ field chung vào các bảng concrete subtype.
- Database có khả năng xử lý JOIN tốt và workload chấp nhận số bảng liên quan.

### 16.2. Khi nên cân nhắc cách khác

Có thể không nên chọn JOINED khi:

- Cây kế thừa quá sâu, rất nhiều subtype và phần lớn truy vấn đọc từ root.
- Workload chủ yếu là báo cáo lớn, yêu cầu SQL cực đơn giản và độ trễ rất thấp.
- Các loại nghiệp vụ nhìn giống nhau nhưng **không có quan hệ is-a thực sự**, chỉ trùng vài field.
- Dữ liệu một subtype được truy cập, phân quyền, nâng cấp schema và vận hành hoàn toàn độc lập với subtype khác.

Trong trường hợp cuối, **composition** với `@Embeddable`, nhiều entity riêng biệt hoặc `@MappedSuperclass` có thể rõ ràng hơn inheritance.

## 17. JOINED và @SecondaryTable không phải một

JPA còn có `@SecondaryTable` để chia **một entity** thành nhiều bảng:

```java
@Entity
@Table(name = "users")
@SecondaryTable(name = "user_profiles")
public class User {
    @Id
    private Long id;

    @Column(table = "user_profiles")
    private String biography;
}
```

Ở đây không có subclass `UserProfile extends User`. `User` là một entity được lưu trong hai bảng.

So sánh:

- **`@SecondaryTable`**: chia **thuộc tính của cùng một lớp entity** qua nhiều bảng.
- **`InheritanceType.JOINED`**: chia **thuộc tính chung và riêng của nhiều entity types trong hệ kế thừa** qua các bảng.

Cả hai có thể dùng PK join nhưng **lý do thiết kế khác nhau**. Không tạo hierarchy chỉ vì muốn tách một nhóm cột hiếm dùng sang bảng khác; có thể cân nhắc secondary table khi thích hợp.

## 18. Quản lý schema và migration với JOINED

Trong dự án thực tế, schema thường được quản lý bằng Flyway, Liquibase hoặc quy trình migration thay vì dựa hoàn toàn vào tính năng tự tạo bảng của ORM.

### 18.1. Tạo bảng gốc trước bảng con

Vì `books.publication_id` tham chiếu `publications.id`, khi tạo schema nên:

1. Tạo bảng gốc `publications`.
2. Tạo bảng `books` với PK và FK tới bảng gốc.
3. Tạo bảng `magazines` với PK và FK tới bảng gốc.
4. Thêm unique constraint, index và dữ liệu tham chiếu phù hợp.

Khi xóa schema, thứ tự thường ngược lại nếu không dùng cơ chế cascade DDL thích hợp.

### 18.2. Thêm một subclass mới

Giả sử thêm `AudioBook extends Publication` với `durationMinutes`. Trong JOINED có thể cần:

```sql
CREATE TABLE audio_books (
    publication_id BIGINT PRIMARY KEY,
    duration_minutes INTEGER NOT NULL,
    CONSTRAINT fk_audio_books_publications
        FOREIGN KEY (publication_id)
        REFERENCES publications(id)
);
```

Và class:

```java
@Entity
@Table(name = "audio_books")
@PrimaryKeyJoinColumn(
    name = "publication_id",
    referencedColumnName = "id"
)
public class AudioBook extends Publication {
    @Column(name = "duration_minutes", nullable = false)
    private int durationMinutes;

    protected AudioBook() {
    }

    public AudioBook(
            String title,
            String publisher,
            int durationMinutes) {
        super(title, publisher);
        this.durationMinutes = durationMinutes;
    }
}
```

Thêm subclass không nhất thiết bắt sửa tất cả cột của bảng gốc, trừ khi còn cần thay đổi discriminator, ràng buộc, index hoặc những field chung. Đây là một lợi ích của JOINED khi hệ phân cấp có subtype mới với trường riêng.

### 18.3. Di chuyển dữ liệu từ SINGLE_TABLE sang JOINED

Nếu trước đây mọi ấn phẩm nằm trong một bảng có discriminator và cột riêng, quá trình chuyển sang JOINED cần lập kế hoạch để **giữ nguyên khóa chính**:

```text
Bảng cũ publications_all
    id, kind, title, publisher, isbn, page_count,
    issue_number, issue_date
                       |
                       v
Bảng mới publications
    id, title, publisher
                       |
                       +--> books(publication_id, isbn, page_count)
                       |
                       +--> magazines(publication_id, issue_number, issue_date)
```

Các bước thường gồm:

- Tạo bảng mới và ràng buộc PK/FK.
- Sao chép các field chung vào bảng gốc.
- Phân loại dữ liệu theo subtype để sao chép field riêng sang đúng bảng subclass.
- Giữ ID nhất quán, cập nhật nguồn cấp ID nếu sử dụng sequence/identity.
- Chuyển các khóa ngoại của entity khác sang tham chiếu đúng bảng gốc khi phù hợp.
- Đồng bộ cấu hình discriminator nếu dùng.
- Lập kế hoạch triển khai/rollback với transaction, thời gian bảo trì hoặc cơ chế migration online phù hợp.

**Không nên chỉ đổi `@Inheritance(strategy = JOINED)` rồi khởi động trên schema SINGLE_TABLE cũ mà kỳ vọng JPA tự di chuyển dữ liệu chính xác.** Đó là thay đổi mô hình lưu trữ cần migration có kiểm soát.

### 18.4. Đổi tên cột PK của bảng subclass

Nếu class dùng:

```java
@PrimaryKeyJoinColumn(name = "publication_id", referencedColumnName = "id")
```

thì migration phải tạo `books.publication_id`. Nếu bảng thực tế dùng `id`, cần sửa annotation hoặc schema cho khớp.

Đổi tên cột PK/FK có thể ảnh hưởng index, constraint, query native, view và integration khác. Đừng thay tên annotation mà bỏ qua migration dữ liệu.

## 19. Những lỗi thường gặp khi dùng JOINED

### Lỗi 1 — Quên @Inheritance(strategy = JOINED) ở root

```java
@Entity
public abstract class Publication {
    @Id
    private Long id;
}
```

Nếu root không chọn chiến lược, JPA mặc định sử dụng `SINGLE_TABLE` cho entity inheritance theo đặc tả. Vì vậy, chỉ tạo các subclass `@Entity` không đủ để chắc chắn có bảng riêng cho mỗi subtype.

### Lỗi 2 — Biến root thành @MappedSuperclass nhưng vẫn mong có bảng root

`@MappedSuperclass` không tạo entity gốc đa hình. Nếu muốn `publications` chứa field chung và `Book`/`Magazine` nối đến nó bằng FK/PK, root phải là `@Entity` trong hệ JOINED.

### Lỗi 3 — Khai báo @Id riêng ở mỗi subclass

```java
// Sai ý tưởng đối với JOINED hierarchy:
// Publication đã có @Id Long id.
@Entity
public class Book extends Publication {
    @Id
    @GeneratedValue
    private Long bookId;
}
```

Một subclass trong hệ phân cấp không cần khóa chính JPA khác với khóa inherited. Nó phải dùng cùng ID để nối bảng.

### Lỗi 4 — Tạo khóa chính mới cho bảng subclass mà không ràng buộc shared PK

Nếu bảng `books` vừa có `id` identity riêng vừa có `publication_id` FK độc lập, schema không còn phản ánh đúng mô hình `JOINED` shared primary key đang dùng. Hãy đặt `publication_id` làm **PRIMARY KEY và FOREIGN KEY**.

### Lỗi 5 — Nhầm @PrimaryKeyJoinColumn với @JoinColumn của association

`@PrimaryKeyJoinColumn` trong hierarchy nối **bảng của cùng một entity qua kế thừa**. `@JoinColumn` trên `@ManyToOne` thường nối **hai entity khác nhau** trong một association.

Đừng khai báo `Book` là `@OneToOne Publication` chỉ để thay cho `extends Publication` nếu domain thực sự cần entity inheritance và truy vấn đa hình.

### Lỗi 6 — Nghĩ JOINED luôn phải có discriminator

Trong JOINED, discriminator không nhất thiết là bắt buộc trong mọi mapping/provider. Nếu dùng, hãy khai báo và quản lý cột rõ ràng, hiểu cách provider xử lý và không nhầm nó với shared PK/FK.

### Lỗi 7 — Nghĩ truy vấn root chỉ đọc bảng root

`SELECT p FROM Publication p` cần trả object có subtype thực tế. Provider có thể phải làm thêm JOIN hoặc xử lý nhận diện subtype. Không giả định mọi trường hợp chỉ có một `SELECT * FROM publications` đơn giản.

### Lỗi 8 — Nghĩ persist Book chỉ chèn vào bảng books

Trong JOINED, dữ liệu chung của Book được lưu ở bảng `publications`. Persist một Book mới phải phản ánh cả phần chung lẫn riêng.

### Lỗi 9 — Nghĩ xóa hàng books là đủ để xóa Book entity

Một entity `Book` trải qua nhiều bảng. Xóa entity phải xử lý đầy đủ các hàng cấu thành entity theo mapping và transaction.

### Lỗi 10 — Không tạo đúng FK cho bảng subclass

Nếu `books.publication_id` không có FK đến `publications.id`, dữ liệu từ writer bên ngoài có thể tạo hàng subclass mồ côi. Cần constraint database phù hợp để bảo vệ shared identity.

### Lỗi 11 — Cho rằng FK/PK tự bảo đảm đúng một subtype trên mỗi root

PK/FK của từng bảng con không tự ngăn cùng ID xuất hiện ở **hai bảng subclass khác nhau**, hoặc một root không có subclass dù root abstract. Nếu có đường ghi ngoài JPA, cần bảo vệ invariant bằng mô hình và kiểm soát dữ liệu riêng.

### Lỗi 12 — Dùng Hibernate-specific behavior như quy tắc tuyệt đối của JPA

Tên sequence tự động, cách nhận diện subtype, số câu SQL JOIN, proxy và batching có thể khác giữa provider/phiên bản. Hãy phân biệt **hợp đồng JPA** với **chi tiết thực thi provider**.

### Lỗi 13 — Xem subclass field nullable vì không có ở subtype khác

Trong JOINED, mỗi subtype có bảng riêng, nên `books.isbn NOT NULL` không gây khó khăn cho `Magazine`. Không cần cho phép NULL trên mọi cột riêng chỉ vì hệ có nhiều subtype.

### Lỗi 14 — Nhầm JOINED inheritance với join fetch quan hệ

`JOINED` trong `InheritanceType.JOINED` là chiến lược lưu entity inheritance. `JOIN FETCH` của JPQL là công cụ lấy association trong truy vấn. Một loại không tự kích hoạt loại kia và không thay thế quyết định `FetchType.LAZY/EAGER`.

### Lỗi 15 — Bỏ qua chi phí truy vấn đa hình ở hierarchy lớn

Nhiều subtype và nhiều tầng kế thừa có thể tạo SQL phức tạp. Nên quan sát các truy vấn có tần suất cao, dùng subtype-specific query hoặc projection nếu chỉ cần một phần dữ liệu.

## 20. Tình huống thực hành có hướng dẫn

### Tình huống A — Lưu một Book mới

Ứng dụng tạo:

```java
Book book = new Book(
    "Thiết kế hệ thống",
    "Nhà xuất bản C",
    "978-9-8765",
    580
);

entityManager.persist(book);
```

**Câu hỏi:** Cần những hàng nào trong database?

**Giải thích:** Một hàng `publications` chứa `id`, `title`, `publisher`, `version`; một hàng `books` có `publication_id` bằng ID root, `isbn` và `page_count`. Cả hai thuộc cùng entity Book.

### Tình huống B — Truy vấn Publication

```java
List<Publication> result = entityManager.createQuery(
    "SELECT p FROM Publication p",
    Publication.class
).getResultList();
```

**Câu hỏi:** Có thể nhận được instance `Book` và `Magazine` không?

**Giải thích:** Có. Đây là truy vấn đa hình trên entity root. JPA có thể trả subtype thực tế theo dữ liệu đã lưu và mapping của hệ phân cấp.

### Tình huống C — Chỉ thay đổi ISBN

```java
Book book = entityManager.find(Book.class, id);
// Giả sử entity có phương thức changeIsbn(newIsbn).
```

**Câu hỏi:** Field ISBN thuộc bảng nào?

**Giải thích:** `books` vì `isbn` được khai báo tại subclass `Book`. Nếu phiên bản entity được quản lý bằng `@Version` ở root, provider còn phải xử lý optimistic locking theo mô hình entity, không chỉ phụ thuộc cột ISBN.

### Tình huống D — Thêm một subtype mới

Thêm `AudioBook` có `durationMinutes`.

**Câu hỏi:** Có nhất thiết tạo thêm `duration_minutes` nullable vào bảng gốc `publications` không?

**Giải thích:** Không với JOINED. Có thể tạo bảng `audio_books` có cột `duration_minutes` và shared PK/FK tới root.

### Tình huống E — Một external writer chèn dữ liệu lỗi

Một script chèn:

```text
publications.id = 50
books.publication_id = 50
magazines.publication_id = 50
```

**Câu hỏi:** PK/FK đơn giản có chắc chắn từ chối không?

**Giải thích:** Không. Mỗi bảng subclass chỉ thấy một hàng có ID 50 và FK đều trỏ đến root hợp lệ. Phải có kiểm soát riêng nếu cần bảo đảm một ID chỉ thuộc đúng một subtype.

### Tình huống F — Một entity khác tham chiếu Publication

`ReadingListItem.publication` có kiểu `Publication`.

**Câu hỏi:** Cột khóa ngoại nên trỏ đến bảng nào nếu muốn chấp nhận mọi subtype?

**Giải thích:** Thông thường là bảng gốc `publications` vì mọi Book/Magazine cùng có ID ở đó. Khi tải association, JPA xử lý subtype thực tế theo mapping.

### Tình huống G — Thiết kế dữ liệu chỉ có hai field chung

Một hệ thống có 30 loại tài liệu khác nhau, chỉ giống nhau ở `createdAt` và `createdBy`, còn mọi hành vi/truy vấn đều tách biệt.

**Câu hỏi:** JOINED có nhất thiết là lựa chọn tốt nhất?

**Giải thích:** Không. Nếu không có quan hệ is-a thực sự hoặc không cần truy vấn đa hình, `@MappedSuperclass` hoặc composition có thể đơn giản và ít JOIN hơn. Không nên dùng inheritance chỉ để tái sử dụng một vài thuộc tính.

## 21. Câu hỏi tự kiểm tra

**1. `InheritanceType.JOINED` lưu thuộc tính chung và riêng ở đâu?**

Thuộc tính chung nằm trong bảng của entity gốc; thuộc tính riêng nằm trong bảng subclass tương ứng. Các bảng liên kết bằng khóa chính/khóa ngoại có cùng giá trị.

**2. Trong `books`, `publication_id` có phải ID độc lập với `publications.id` không?**

Không. Nó là shared primary key: khóa chính của bảng con đồng thời là khóa ngoại tham chiếu ID root.

**3. Có cần khai báo lại `@Id` trong `Book extends Publication` không?**

Không. `Book` thừa hưởng ID từ root `Publication`, chỉ thêm các field riêng và mapping bảng subclass.

**4. Vì sao `SELECT p FROM Publication p` có thể tốn nhiều JOIN?**

Vì query trên root có tính đa hình, provider cần nhận diện và dựng các loại subclass thực tế. Với JOINED, dữ liệu subclass ở nhiều bảng riêng.

**5. `@PrimaryKeyJoinColumn` dùng để làm gì?**

Để chỉ định cột khóa chính của bảng subclass tham chiếu khóa chính bảng cha, đặc biệt khi muốn tên cột khác quy ước mặc định.

**6. Discriminator có thay thế shared PK/FK trong JOINED không?**

Không. Discriminator là thông tin nhận diện subtype; shared PK/FK mới biểu diễn quan hệ giữa các hàng lưu cùng entity.

**7. `@MappedSuperclass` có tạo bảng gốc JOINED và hỗ trợ `SELECT p FROM Base p` không?**

Không. `@MappedSuperclass` không phải entity, không có bảng độc lập và không là root entity query đa hình.

**8. Khi xóa một `Book` bằng `EntityManager.remove()`, phải xử lý những bảng nào?**

Các hàng cấu thành entity trong bảng `books` và `publications` theo mapping và transaction. Không xóa riêng một bảng nếu muốn xóa toàn bộ entity.

**9. Vì sao JOINED thuận lợi hơn SINGLE_TABLE khi một subclass có field bắt buộc?**

Vì field riêng có bảng riêng, nên có thể dùng `NOT NULL` trên cột đó mà không buộc các subtype khác phải có giá trị tương ứng.

**10. Một FK từ `reading_list_items` muốn tham chiếu mọi loại Publication thì thường trỏ đâu?**

Trỏ đến `publications.id` ở bảng root. JPA xử lý loại subtype của entity được tham chiếu.

**11. Khi thêm subclass, chỉ tạo class Java là đủ chưa?**

Chưa nếu schema được quản lý bằng migration. Cần tạo bảng subclass có shared PK/FK và các cột riêng, đồng bộ cấu hình JPA và dữ liệu hiện có.

**12. Có thể dựa vào IDENTITY generator ở bảng books để cấp ID mới riêng cho Book không?**

Không theo mô hình JOINED minh họa. Generator cấp ID tại root, và bảng subclass dùng **cùng giá trị** đó; không có ID thứ hai độc lập.

## 22. Ghi nhớ cốt lõi

**`InheritanceType.JOINED` ánh xạ một hệ phân cấp entity thành nhiều bảng liên kết theo cùng một định danh.** Bảng root chứa `@Id` và các thuộc tính chung; mỗi bảng subclass chứa những thuộc tính riêng; khóa chính của bảng subclass đồng thời là khóa ngoại tới bảng cha. Một object `Book` có thể trải qua hai hoặc nhiều hàng ở các bảng khác nhau nhưng vẫn chỉ là **một entity trong JPA**.

Đặt `@Inheritance(strategy = InheritanceType.JOINED)` trên entity root, đánh dấu subclass bằng `@Entity` và dùng `@PrimaryKeyJoinColumn` nếu cần đặt tên cột nối rõ ràng. JPA hỗ trợ truy vấn đa hình từ root bằng JPQL và truy vấn trực tiếp subclass; provider sẽ thực hiện các phép kết hợp dữ liệu thích hợp. Không nhầm cơ chế này với cascade giữa các entity, `@SecondaryTable` hay `JOIN FETCH` trên association.

JOINED là một lựa chọn phù hợp khi cần **kế thừa đúng nghĩa, truy vấn đa hình, dữ liệu chung không lặp lại và ràng buộc riêng cho từng subtype**. Đổi lại, cần quan tâm **JOIN và số lệnh SQL, khóa sinh tại root, PK/FK ở bảng con, optimistic locking, hiệu năng và migration**. Thiết kế đúng cả Java hierarchy lẫn schema database sẽ giúp lưu, đọc, cập nhật và xóa entity kế thừa một cách nhất quán.
