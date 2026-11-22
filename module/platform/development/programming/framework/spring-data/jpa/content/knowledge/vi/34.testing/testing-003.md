# Tạo dữ liệu thử nghiệm bằng TestEntityManager

## Mục tiêu

Trong kiểm thử persistence, dữ liệu đầu vào phải được tạo theo đúng mapping JPA để repository và service có thể chạy trên database. Spring Boot cung cấp `TestEntityManager` như một tiện ích dành riêng cho test, bao quanh một số thao tác thường dùng của `EntityManager` và bổ sung các helper để persist, flush, lấy ID và đọc lại entity.

`TestEntityManager` đặc biệt hữu ích trong `@DataJpaTest`: test có thể tạo fixture trực tiếp qua JPA, buộc dữ liệu xuống database, xóa persistence context rồi gọi repository để xác nhận kết quả. Cách làm này giúp kiểm tra query thực sự chạy với dữ liệu đã lưu thay vì chỉ đọc lại object còn nằm trong bộ nhớ.

Sau bài này, bạn có thể:

- Phân biệt `TestEntityManager` với repository và `EntityManager` thông thường.
- Tiêm TestEntityManager vào test slice JPA.
- Tạo dữ liệu bằng `persist`, `persistAndFlush` và `persistAndGetId`.
- Dùng `flush`, `clear`, `find` và `refresh` đúng mục đích.
- Thiết lập fixture có quan hệ và cascade đúng phía sở hữu.
- Kiểm thử repository sau khi dữ liệu đã được ghi xuống database.
- Hiểu transaction rollback của `@DataJpaTest`.
- Tránh false positive do first-level cache, dữ liệu test dùng chung và thứ tự chạy test.
- Chọn embedded database hoặc Testcontainers phù hợp với production.

Ví dụ sử dụng Java 17+, Spring Boot 3.x, Jakarta Persistence và Spring Data JPA. API và package của TestEntityManager thay đổi giữa các major version Spring Boot; hãy kiểm tra version của dự án.

## 1. TestEntityManager là gì?

`TestEntityManager` là tiện ích trong Spring Boot test support, cung cấp một tập con các thao tác của JPA `EntityManager` cùng các helper dành cho việc chuẩn bị và xác minh dữ liệu thử nghiệm.

Trong Spring Boot 3.x, import:

```java
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
```

Trong Spring Boot 4.x, package đã chuyển sang:

```java
import org.springframework.boot.jpa.test.autoconfigure.TestEntityManager;
```

Không thêm cả hai import vào cùng một class. Dùng package tương ứng với Spring Boot version mà dự án đang chạy.

Các thao tác thường dùng:

| Method | Mục đích |
|---|---|
| `persist(entity)` | Đưa entity mới vào persistence context ở trạng thái managed |
| `persistAndFlush(entity)` | Persist entity và flush ngay |
| `persistAndGetId(entity, Long.class)` | Persist và trả về ID |
| `persistFlushFind(entity)` | Persist, flush rồi find theo ID |
| `flush()` | Đồng bộ thay đổi đang chờ xuống database |
| `clear()` | Detach toàn bộ entity trong persistence context |
| `find(Type.class, id)` | Tìm entity theo primary key |
| `refresh(entity)` | Nạp lại trạng thái entity từ database |
| `detach(entity)` | Detach một entity |
| `merge(entity)` | Merge trạng thái của object vào persistence context |
| `remove(entity)` | Đánh dấu entity managed để xóa |
| `getId(entity)` | Lấy identifier của entity |
| `getEntityManager()` | Lấy EntityManager nền mà TestEntityManager sử dụng |

`TestEntityManager` không phải một database giả và cũng không mock repository. Nó sử dụng persistence infrastructure và JPA provider được cấu hình cho test.

## 2. Tạo test slice với @DataJpaTest

`@DataJpaTest` cấu hình một test slice tập trung vào JPA: entity mapping, repository và các thành phần persistence liên quan.

Ví dụ:

```java
package com.example.demo.book;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest
class BookRepositoryTest {

    @Autowired
    private TestEntityManager testEntityManager;

    @Autowired
    private BookRepository bookRepository;

    @Test
    void testContextStarts() {
        // TestEntityManager và repository đã được inject.
    }
}
```

Trong ví dụ này, `TestEntityManager` và `BookRepository` cùng tham gia test transaction do Spring quản lý. Mỗi test method thường chạy trong một transaction và transaction được rollback khi test kết thúc.

`@DataJpaTest` thường dùng embedded database nếu dependency phù hợp có mặt. Nếu muốn chạy trên database Testcontainers hoặc database tương ứng production, cấu hình test datasource rõ ràng; ví dụ với Testcontainers có thể dùng `@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)` để không bị thay datasource đã cấu hình.

Không dùng `@DataJpaTest` để kiểm thử toàn bộ HTTP/controller/security stack. Nó chỉ tập trung vào persistence. Nếu cần kiểm tra service có transaction, event hoặc nhiều bean phối hợp, có thể dùng `@SpringBootTest` hoặc test slice phù hợp.

## 3. Entity và repository mẫu

Dùng một entity Book có ID tự sinh, tiêu đề, ISBN và quan hệ to-one tới Author cùng Publisher. Publisher là association tùy chọn để minh họa fixture nhiều cấp ở phần sau.

Author:

```java
package com.example.demo.book;

import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "authors")
public class Author {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    @OneToMany(
        mappedBy = "author",
        cascade = CascadeType.PERSIST,
        orphanRemoval = true
    )
    private List<Book> books = new ArrayList<>();

    protected Author() {
    }

    public Author(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void addBook(Book book) {
        books.add(book);
        book.setAuthor(this);
    }
}
```

Book:

```java
package com.example.demo.book;

import jakarta.persistence.*;

@Entity
@Table(
    name = "books",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_books_isbn",
        columnNames = "isbn"
    )
)
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 200)
    private String title;

    @Column(nullable = false, length = 20)
    private String isbn;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "author_id", nullable = false)
    private Author author;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "publisher_id")
    private Publisher publisher;

    protected Book() {
    }

    public Book(String title, String isbn, Author author) {
        this(title, isbn, author, null);
    }

    public Book(
            String title,
            String isbn,
            Author author,
            Publisher publisher
    ) {
        this.title = title;
        this.isbn = isbn;
        this.author = author;
        this.publisher = publisher;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public String getIsbn() {
        return isbn;
    }

    public Author getAuthor() {
        return author;
    }

    public void setAuthor(Author author) {
        this.author = author;
    }
}
```

Publisher:

```java
package com.example.demo.book;

import jakarta.persistence.*;

@Entity
@Table(name = "publishers")
public class Publisher {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    protected Publisher() {
    }

    public Publisher(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

Repository:

```java
package com.example.demo.book;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository extends JpaRepository<Book, Long> {

    List<Book> findByTitleContainingIgnoreCase(String title);

    Optional<Book> findByIsbn(String isbn);
}
```

Các ví dụ sau dùng entity và repository này. Constructor public giúp fixture tạo object dễ đọc; constructor không tham số vẫn được giữ ở protected để JPA khởi tạo entity.

## 4. Inject TestEntityManager và persist fixture

Dùng `persist` để đưa entity mới vào persistence context:

```java
@Test
void persistsBook() {
    Author author =
            testEntityManager.persist(new Author("Ada Lovelace"));

    Book book = testEntityManager.persistAndFlush(
            new Book(
                    "Spring Data JPA",
                    "9780000000001",
                    author
            )
    );

    assertThat(book.getId()).isNotNull();
}
```

`persist` gọi thao tác persist của JPA. Entity trở thành managed trong persistence context hiện tại. Tuy nhiên, điều đó không có nghĩa mọi thay đổi đã được gửi xuống database ngay tại dòng lệnh đó.

ID có thể được cấp ngay hoặc khi insert được thực thi, tùy chiến lược sinh ID và provider. Không viết test giả định mọi ID đều bắt đầu từ 1 hoặc tăng đúng một đơn vị; sequence/identity và dữ liệu test có thể làm giá trị khác nhau.

### 4.1. Persist nhiều fixture rồi flush một lần

Khi tạo nhiều dữ liệu nền, có thể persist từng entity và flush sau cùng:

```java
@Test
void createsSeveralBooks() {
    Author author =
            testEntityManager.persist(new Author("Ada Lovelace"));

    testEntityManager.persist(
            new Book("Spring Data JPA", "9780000000001", author)
    );
    testEntityManager.persist(
            new Book("Hibernate Basics", "9780000000002", author)
    );
    testEntityManager.persist(
            new Book("JPA in Practice", "9780000000003", author)
    );

    testEntityManager.flush();
}
```

Cách này tránh flush sau từng fixture khi không cần thiết. Database sẽ nhận các thao tác pending khi flush được gọi hoặc khi provider tự flush trước một query cần đồng bộ dữ liệu.

### 4.2. Dùng persistAndFlush

Nếu muốn ghi ngay một fixture và phát hiện lỗi constraint tại vị trí cụ thể:

```java
Author author = testEntityManager.persistAndFlush(
        new Author("Ada Lovelace")
);
```

`persistAndFlush` tương đương gọi persist rồi flush. Nó hữu ích khi:

- Cần ID do database/provider cấp trước khi tạo entity phụ thuộc.
- Cần constraint violation xuất hiện ngay trong bước setup.
- Muốn chắc chắn dữ liệu đã được gửi xuống database trước khi chạy query.
- Muốn tách các giai đoạn fixture để xác định lỗi dễ hơn.

Flush vẫn không phải commit. Transaction có thể tiếp tục và rollback ở cuối test.

## 5. Lấy ID bằng persistAndGetId và getId

Có thể lấy ID ngay khi persist:

```java
Long authorId = testEntityManager.persistAndGetId(
        new Author("Ada Lovelace"),
        Long.class
);
```

Hoặc lấy ID từ entity đã persist:

```java
Author author = testEntityManager.persist(
        new Author("Ada Lovelace")
);

Long authorId = testEntityManager.getId(author, Long.class);
```

Cách này hữu ích khi fixture cần ID để truyền vào query hoặc để tạo entity liên quan bằng foreign key thông qua API phù hợp.

Không ép kiểu ID bằng giả định nếu entity dùng UUID, composite key hoặc kiểu khác. Dùng overload có tham số class để thể hiện kiểu ID mong muốn. Nếu ID chưa được sinh theo strategy đang dùng, giá trị có thể chưa có cho đến khi insert được thực hiện.

## 6. Flush, clear và find: kiểm tra dữ liệu thật sự đã lưu

Đây là chuỗi thao tác quan trọng nhất khi test repository:

1. Persist fixture.
2. Flush để gửi thay đổi xuống database.
3. Clear persistence context để detach các entity đang managed.
4. Gọi repository hoặc find để đọc lại.

Ví dụ:

```java
@Test
void readsBookFromDatabaseAfterPersisting() {
    Author author =
            testEntityManager.persistAndFlush(
                    new Author("Ada Lovelace")
            );

    Book book = testEntityManager.persist(
            new Book(
                    "Spring Data JPA",
                    "9780000000001",
                    author
            )
    );

    testEntityManager.flush();
    Long bookId = book.getId();

    testEntityManager.clear();

    Book reloaded = bookRepository.findById(bookId)
            .orElseThrow();

    assertThat(reloaded.getTitle()).isEqualTo("Spring Data JPA");
    assertThat(reloaded.getAuthor().getName()).isEqualTo("Ada Lovelace");
}
```

### 6.1. Vì sao cần clear?

JPA persistence context là first-level cache. Nếu gọi `find` hoặc repository `findById` khi entity vẫn còn managed, provider thường trả lại chính object đã có trong context thay vì đọc lại trạng thái từ database.

Điều đó có thể tạo false positive: test thấy giá trị vừa set trên object và tưởng rằng database đã lưu đúng.

`clear()` detach toàn bộ entity managed trong context hiện tại. Sau đó, query đọc entity phải nạp trạng thái từ database trong transaction. Đây là cách hữu ích để xác nhận mapping, insert/update và query.

Lưu ý: `clear()` tác động tới toàn bộ persistence context, không chỉ entity vừa tạo. Các thay đổi chưa flush sẽ không còn được quản lý để tự động ghi. Vì vậy, gọi flush trước clear nếu muốn giữ các thay đổi đó.

### 6.2. Flush không phải commit

`flush()` đồng bộ các thay đổi trong persistence context với database connection/transaction hiện tại. Nó không kết thúc transaction và không làm dữ liệu trở nên bền vững với transaction khác.

Trong `@DataJpaTest`, transaction thường rollback sau test. Do đó:

- Sau flush, query trong cùng transaction có thể nhìn thấy dữ liệu đã ghi.
- Test method khác không nên phụ thuộc dữ liệu fixture của test trước.
- Transaction rollback sẽ dọn các thay đổi test theo cơ chế database/transaction.
- Constraint được trì hoãn đến commit (nếu database hỗ trợ deferred constraint) có thể chưa phát sinh lỗi tại flush.

Không dùng flush như một cách để giữ dữ liệu test lại sau khi test kết thúc.

## 7. persistFlushFind có gì khác?

`persistFlushFind(entity)` là helper gộp ba thao tác:

1. Persist entity.
2. Flush persistence context.
3. Find entity theo ID của object đó.

Ví dụ:

```java
Book found = testEntityManager.persistFlushFind(
        new Book(
                "Spring Data JPA",
                "9780000000001",
                author
        )
);
```

Helper này thuận tiện khi cần persist và gọi find ngay. Tuy nhiên, nó không clear persistence context trước khi find. Vì entity vừa persist vẫn có thể đang managed, `find` có thể trả lại cùng instance đã có trong first-level cache.

Nếu mục tiêu là chứng minh query đọc được dữ liệu từ database sau khi ghi, dùng chuỗi rõ ràng:

```java
Book saved = testEntityManager.persistAndFlush(book);
Long id = saved.getId();

testEntityManager.clear();

Book reloaded = testEntityManager.find(Book.class, id);
```

Hoặc clear rồi gọi repository method đang được kiểm thử. Như vậy, test tránh nhầm giữa trạng thái object trong bộ nhớ và dữ liệu được nạp lại.

## 8. Tạo fixture có quan hệ đúng phía sở hữu

JPA chỉ đồng bộ association dựa trên mapping và phía sở hữu (owning side). Với `@ManyToOne` và `@OneToMany(mappedBy = ...)`, phía có `@JoinColumn` thường là owning side.

Trong ví dụ:

- Book.author là owning side vì Book có `@JoinColumn(name = "author_id")`.
- Author.books (nếu có) là inverse side vì khai báo `mappedBy = "author"`.

Nếu entity có quan hệ hai chiều, helper domain nên cập nhật cả hai phía:

```java
@Entity
public class Author {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToMany(
        mappedBy = "author",
        cascade = CascadeType.PERSIST,
        orphanRemoval = true
    )
    private List<Book> books = new ArrayList<>();

    public void addBook(Book book) {
        books.add(book);
        book.setAuthor(this);
    }
}
```

Trong fixture:

```java
Author author = new Author("Ada Lovelace");
Book book = new Book(
        "Spring Data JPA",
        "9780000000001",
        author
);

author.addBook(book);

testEntityManager.persistAndFlush(author);
```

Ví dụ này giả định Book có setter hoặc phương thức gán Author phù hợp. Cascade PERSIST cho phép persist Author kéo theo Book; nếu không có cascade, phải persist từng entity theo thứ tự phù hợp.

Không chỉ thêm Book vào inverse collection rồi mong database tự cập nhật foreign key. Phải gán owning side. Nếu không, sau khi clear và reload, quan hệ có thể không tồn tại dù collection trong object ban đầu trông có vẻ đúng.

### 8.1. Tạo fixture cho quan hệ nhiều cấp

Với quan hệ nhiều cấp, tạo parent trước khi child nếu child cần parent đã persist:

```java
Author author = testEntityManager.persist(
        new Author("Ada Lovelace")
);

Publisher publisher = testEntityManager.persist(
        new Publisher("Example Press")
);

Book book = testEntityManager.persist(
        new Book(
                "Spring Data JPA",
                "9780000000001",
                author,
                publisher
        )
);

testEntityManager.flush();
testEntityManager.clear();
```

Nếu mapping có cascade phù hợp, có thể persist aggregate root và để cascade lưu các thành phần. Hãy chọn một cách rõ ràng, tránh vừa cascade vừa persist lại cùng entity một cách không cần thiết.

Với `@ManyToMany`, phải cập nhật owning side của join table. Với `@OneToOne`, xác định entity nào chứa join column. Khi fixture phức tạp, viết factory/helper có tên thể hiện aggregate được tạo để test dễ đọc.

## 9. Dùng TestEntityManager trong @BeforeEach

Có thể tạo dữ liệu dùng chung cho các test bằng `@BeforeEach`:

```java
@DataJpaTest
class BookRepositoryTest {

    @Autowired
    private TestEntityManager testEntityManager;

    @Autowired
    private BookRepository bookRepository;

    @BeforeEach
    void setUp() {
        Author author = testEntityManager.persist(
                new Author("Ada Lovelace")
        );

        testEntityManager.persist(
                new Book("Spring Data JPA", "9780000000001", author)
        );
        testEntityManager.persist(
                new Book("Hibernate Basics", "9780000000002", author)
        );

        testEntityManager.flush();
        testEntityManager.clear();
    }

    @Test
    void findsBookByTitle() {
        List<Book> result =
                bookRepository.findByTitleContainingIgnoreCase("spring");

        assertThat(result)
                .extracting(Book::getTitle)
                .containsExactly("Spring Data JPA");
    }
}
```

Vì mỗi test method thường có transaction riêng và rollback sau khi kết thúc, fixture được tạo trong `@BeforeEach` sẽ được tạo lại cho từng test. Cách này giúp test độc lập, dù có thể tốn thời gian nếu fixture rất lớn.

Không tạo dữ liệu dùng chung bằng một transaction đã commit rồi để các test phụ thuộc thứ tự chạy. Test phải tự thiết lập dữ liệu cần thiết để có thể chạy độc lập.

## 10. Kiểm thử constraint và lỗi khi flush

Nhiều lỗi chỉ xuất hiện khi provider gửi SQL xuống database. Ví dụ ISBN có unique constraint:

```java
@Test
void duplicateIsbnViolatesUniqueConstraint() {
    Author author = testEntityManager.persist(
            new Author("Ada Lovelace")
    );

    testEntityManager.persistAndFlush(
            new Book("Spring Data JPA", "9780000000001", author)
    );

    assertThatThrownBy(() -> testEntityManager.persistAndFlush(
            new Book(
                    "Another Book",
                    "9780000000001",
                    author
            )
    )).isInstanceOf(RuntimeException.class);
}
```

Ví dụ này minh họa thời điểm lỗi thường xuất hiện; exception class cụ thể có thể phụ thuộc JPA provider, database và cách Spring dịch lỗi. Nếu test một service/repository boundary, nên kiểm tra exception Spring được dịch ra ở boundary đó thay vì khẳng định một exception nội bộ của Hibernate.

Sau khi flush thất bại, transaction/persistence context có thể ở trạng thái không thể tiếp tục sử dụng an toàn. Không bắt lỗi rồi tiếp tục query như thể transaction vẫn bình thường. Hãy để test kết thúc và rollback; nếu cần kiểm tra nhiều trường hợp lỗi độc lập, dùng test method riêng.

## 11. Dùng refresh để đọc lại thay đổi từ database

`refresh(entity)` nạp lại trạng thái của entity đang managed từ database, ghi đè thay đổi trong bộ nhớ chưa được đồng bộ.

Ví dụ database trigger cập nhật một cột:

```java
Book book = testEntityManager.persistAndFlush(new Book(...));

// Trigger hoặc procedure thay đổi một thuộc tính trong database.

testEntityManager.refresh(book);

assertThat(book.getTitle()).isEqualTo("Giá trị hiện có trong database");
```

Không gọi refresh khi object đang có thay đổi chưa flush mà bạn muốn giữ, vì refresh sẽ ghi đè trạng thái đó bằng dữ liệu database.

Khác biệt giữa các thao tác:

| Thao tác | Kết quả |
|---|---|
| `flush()` | Gửi thay đổi đang chờ xuống database |
| `refresh(entity)` | Cập nhật object managed từ database |
| `clear()` | Detach tất cả entity managed |
| `detach(entity)` | Detach một entity |
| `find(Type.class, id)` | Tìm entity; có thể trả object đã managed trong context |

Nếu muốn kiểm tra repository query hoặc mapping sau khi lưu, thường dùng flush + clear + repository call. Nếu chỉ cần đồng bộ một entity đang managed với thay đổi database, refresh có thể phù hợp.

## 12. merge và remove trong test

`merge(entity)` hữu ích khi cần đưa trạng thái của một object detached vào persistence context:

```java
Book detached = testEntityManager.find(Book.class, bookId);
testEntityManager.clear();

detached.setTitle("Updated title");

Book managed = testEntityManager.merge(detached);
testEntityManager.flush();

assertThat(managed.getTitle()).isEqualTo("Updated title");
```

`merge` trả về instance managed sau khi merge. Object đầu vào không tự trở thành managed; hãy tiếp tục làm việc với object được trả về.

Để xóa entity:

```java
Book book = testEntityManager.find(Book.class, bookId);

testEntityManager.remove(book);
testEntityManager.flush();

assertThat(testEntityManager.find(Book.class, bookId)).isNull();
```

`remove` yêu cầu entity managed. Nếu có entity detached, cần tìm lại hoặc merge theo đúng semantics trước khi xóa. Không dùng merge chỉ để xóa một object nếu có thể find entity managed trực tiếp.

## 13. TestEntityManager và repository: dùng công cụ nào?

Hai công cụ có vai trò khác nhau:

| Công việc | Công cụ phù hợp |
|---|---|
| Tạo fixture nhanh theo JPA mapping | TestEntityManager |
| Lấy ID sau khi persist | TestEntityManager.getId hoặc persistAndGetId |
| Flush/clear/refresh trong test | TestEntityManager |
| Kiểm tra query method của repository | Repository đang được test |
| Kiểm tra derived query, JPQL, Specification | Repository |
| Kiểm tra service nghiệp vụ | Gọi service thật; dùng TestEntityManager tạo fixture |
| Kiểm tra HTTP/controller/security | Web test hoặc SpringBootTest phù hợp |
| Kiểm tra migration và dialect production | Test database tương ứng, thường qua Testcontainers |

Ví dụ kiểm thử service:

```java
@Test
void serviceReturnsOnlyActiveBooks() {
    Author author = testEntityManager.persist(
            new Author("Ada Lovelace")
    );

    testEntityManager.persist(
            new Book("Spring Data JPA", "9780000000001", author)
    );
    testEntityManager.persist(
            new Book("Old Book", "9780000000002", author)
    );

    testEntityManager.flush();
    testEntityManager.clear();

    List<Book> result = bookService.findBooksByTitle("spring");

    assertThat(result)
            .extracting(Book::getTitle)
            .containsExactly("Spring Data JPA");
}
```

Đoạn test service giả định service được inject và có method `findBooksByTitle(String)` trả về List<Book>; method này gọi repository để tìm theo tiêu đề. TestEntityManager chỉ chuẩn bị dữ liệu; assertion đi qua service thật để xác nhận logic nghiệp vụ.

Không gọi TestEntityManager thay cho service/repository đang được kiểm thử. Nếu test chỉ gọi EntityManager trực tiếp rồi kết luận repository hoạt động, test chưa kiểm tra repository.

## 14. Transaction và rollback của @DataJpaTest

`@DataJpaTest` thường đánh dấu test transaction và rollback khi test kết thúc. Điều này giúp mỗi test bắt đầu với trạng thái dữ liệu sạch.

Một số điểm cần nhớ:

- `persist` và `flush` vẫn nằm trong transaction test.
- Flush không commit.
- Query trong cùng transaction có thể đọc dữ liệu vừa flush.
- Test khác không nên dựa vào dữ liệu chưa commit của test hiện tại.
- `@Commit` hoặc `@Rollback(false)` thay đổi hành vi cleanup; chỉ dùng khi có lý do kiểm thử cụ thể.
- Test chạy qua nhiều transaction hoặc thread có thể không chia sẻ persistence context.
- Test asynchronous cần thiết kế transaction và visibility riêng.

Nếu cần kiểm tra dữ liệu sau commit hoặc giữa hai transaction, không giả định `clear()` tương đương commit. Clear chỉ detach object khỏi persistence context; nó không kết thúc transaction.

Với test cần kiểm tra transaction boundary, có thể dùng TransactionTemplate hoặc cấu hình test phù hợp để commit/rollback có chủ đích. Tránh làm mọi test repository thành transaction không rollback vì sẽ để lại dữ liệu và gây phụ thuộc giữa lần chạy.

## 15. Dữ liệu thử nghiệm ổn định và dễ bảo trì

Một bộ fixture tốt nên:

- Có giá trị cụ thể và dễ hiểu, không phụ thuộc thời gian hiện tại nếu không cần.
- Dùng ISBN/email/mã duy nhất để không va chạm unique constraint.
- Tạo đủ trường hợp match và non-match cho query.
- Kiểm soát ngày giờ bằng Instant cố định và timezone rõ.
- Không phụ thuộc thứ tự ID do database cấp.
- Thiết lập association qua owning side.
- Tạo dữ liệu đúng mức cần thiết, tránh fixture khổng lồ cho một test nhỏ.
- Không chia sẻ mutable entity giữa các test method.
- Có helper factory khi cùng một aggregate được dùng nhiều lần.

Ví dụ factory:

```java
private Book createBook(
        String title,
        String isbn,
        String authorName
) {
    Author author = testEntityManager.persist(
            new Author(authorName)
    );

    return testEntityManager.persist(
            new Book(title, isbn, author)
    );
}
```

Sử dụng:

```java
@Test
void findsBooksByAuthor() {
    createBook("Spring Data JPA", "9780000000001", "Ada");
    createBook("Hibernate", "9780000000002", "Grace");

    testEntityManager.flush();
    testEntityManager.clear();

    List<Book> result = bookRepository.findByAuthorName("Ada");

    assertThat(result)
            .extracting(Book::getTitle)
            .containsExactly("Spring Data JPA");
}
```

Factory nên giữ tên và tham số theo nghiệp vụ. Không tạo helper quá tổng quát với hàng chục tham số nullable khiến người đọc khó biết fixture thực tế chứa dữ liệu gì.

## 16. Embedded database và Testcontainers

Embedded database hữu ích cho test nhanh, nhưng SQL dialect, kiểu dữ liệu, collation, constraint, locking và transaction semantics có thể khác production.

Dùng database tương ứng production khi test phụ thuộc vào:

- Native SQL hoặc stored procedure.
- JSON/array/geospatial hoặc kiểu dữ liệu riêng.
- Function, collation và case sensitivity.
- Lock, isolation, deadlock hoặc constraint đặc thù.
- Migration DDL.
- Generated column, trigger hoặc sequence behavior.

Với Testcontainers, cấu hình container database và để Spring dùng datasource đó. Ví dụ PostgreSQL container:

```java
@Testcontainers
@DataJpaTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE
)
class BookRepositoryPostgresTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    private TestEntityManager testEntityManager;

    @Autowired
    private BookRepository bookRepository;

    // Repository tests...
}
```

Ví dụ cần dependency Testcontainers PostgreSQL, JUnit integration và Spring Boot version hỗ trợ `@ServiceConnection`. Nếu version dự án chưa hỗ trợ annotation này, có thể cấu hình datasource bằng `@DynamicPropertySource`.

Testcontainers giúp test chạy với database thật trong container, nhưng vẫn cần migration và dữ liệu fixture đúng. Không nên giả định một test với embedded H2 chứng minh stored procedure hoặc native SQL PostgreSQL hoạt động.

## 17. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Repository trả object có giá trị cũ | Entity vẫn nằm trong first-level cache | Flush rồi clear trước khi query |
| ID chưa có sau persist | ID strategy/provider chưa insert ngay | Flush hoặc dùng persistAndFlush |
| Constraint violation xuất hiện ở cuối test | SQL chỉ được thực thi khi flush/commit | Flush tại vị trí muốn xác nhận lỗi |
| Quan hệ không được lưu | Chỉ cập nhật inverse side, bỏ qua owning side | Gán association ở phía có JoinColumn |
| Fixture test này ảnh hưởng test khác | Commit dữ liệu hoặc dùng database không được cleanup | Dùng transaction rollback và fixture riêng |
| refresh làm mất thay đổi | Refresh ghi đè trạng thái object bằng database | Flush trước nếu cần giữ thay đổi |
| merge không cập nhật object đầu vào | Merge trả instance managed khác | Dùng object được merge trả về |
| clear làm mất thay đổi pending | Clear detach entity trước khi flush | Flush trước clear |
| TestEntityManager không được inject | Test không chạy trong JPA test configuration hoặc thiếu test support | Kiểm tra @DataJpaTest và dependency |
| Test pass trên H2 nhưng fail production | Khác dialect, driver hoặc database behavior | Dùng Testcontainers với DBMS tương ứng |
| Test phụ thuộc ID cụ thể | Giả định sequence/identity bắt đầu từ một giá trị | Lấy ID từ TestEntityManager |
| Test kiểm tra sai tầng | Dùng TestEntityManager để thay repository/service | Tạo fixture bằng TestEntityManager, gọi thành phần thật đang test |

## 18. Checklist tạo dữ liệu bằng TestEntityManager

- [ ] Test dùng `@DataJpaTest` hoặc cấu hình JPA test phù hợp.
- [ ] TestEntityManager được inject từ Spring Boot test support.
- [ ] Import package đúng với Spring Boot version.
- [ ] Fixture được tạo bằng constructor/factory có ý nghĩa.
- [ ] ID được lấy từ entity hoặc persistAndGetId, không hard-code.
- [ ] Association được gán đúng owning side.
- [ ] Cascade được hiểu rõ trước khi persist aggregate.
- [ ] Flush ở đúng thời điểm cần kiểm tra SQL/constraint.
- [ ] Clear trước khi xác nhận repository query đọc dữ liệu đã lưu.
- [ ] Hiểu flush không phải commit.
- [ ] Dùng refresh khi cần đồng bộ một entity managed từ database.
- [ ] Dùng object trả về từ merge.
- [ ] Không chia sẻ mutable fixture giữa các test.
- [ ] Test không phụ thuộc thứ tự chạy hoặc ID cụ thể.
- [ ] Dùng database tương ứng production cho behavior phụ thuộc dialect.
- [ ] Test đi qua repository/service thật đang được kiểm thử.

## 19. Tài liệu tham khảo

- [Spring Boot 3.5 — TestEntityManager API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/orm/jpa/TestEntityManager.html)
- [Spring Boot — @DataJpaTest](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/autoconfigure/orm/jpa/DataJpaTest.html)
- [Spring Data JPA — Testing](https://docs.spring.io/spring-data/jpa/reference/repositories/testing.html)
- [Jakarta Persistence — EntityManager API](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/entitymanager)

## Kết luận

`TestEntityManager` giúp tạo và điều khiển fixture bằng chính JPA mapping trong các test persistence của Spring Boot. `persist`, `persistAndFlush` và `persistAndGetId` thuận tiện cho việc chuẩn bị dữ liệu; `flush`, `clear`, `find` và `refresh` giúp xác minh trạng thái được đồng bộ giữa persistence context và database.

Với repository test, hãy tạo fixture, flush, clear rồi gọi repository để tránh first-level cache làm test cho kết quả sai lệch. Gán association ở owning side, lấy ID động, giữ mỗi test độc lập và hiểu rằng `@DataJpaTest` thường rollback transaction sau khi test kết thúc. Khi query phụ thuộc dialect, migration hoặc procedure, chạy test trên database tương ứng production bằng Testcontainers. TestEntityManager nên hỗ trợ việc chuẩn bị và xác minh dữ liệu; assertion cuối cùng vẫn cần đi qua repository hoặc service mà test muốn bảo vệ.
