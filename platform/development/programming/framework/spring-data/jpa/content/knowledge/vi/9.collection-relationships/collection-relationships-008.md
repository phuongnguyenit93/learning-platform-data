# CascadeType và phạm vi lan truyền từng thao tác

Trong JPA, một entity có thể tham chiếu tới entity khác. Khi thực hiện thao tác trên entity cha, đôi khi ta muốn thao tác tương ứng được áp dụng cho entity liên quan. Ví dụ, khi lưu một tác giả mới cùng các cuốn sách của người đó, ta muốn lưu cả tác giả và sách trong cùng một luồng nghiệp vụ.

JPA cung cấp **cascade** để lan truyền một số thao tác vòng đời từ entity nguồn sang các entity đích thông qua association. Thuộc tính **cascade** trên annotation quan hệ quyết định thao tác nào được lan truyền.

Các kiểu cascade chuẩn gồm:

- **PERSIST**
- **MERGE**
- **REMOVE**
- **REFRESH**
- **DETACH**
- **ALL** (bao gồm tất cả các thao tác trên)

Cascade giúp quản lý vòng đời của một nhóm entity có quan hệ sở hữu rõ ràng. Tuy nhiên, nó không quyết định entity nào sở hữu foreign key, không thay thế transaction và cũng không đồng nghĩa với **ON DELETE CASCADE** của database. Chọn sai cascade có thể xóa nhầm dữ liệu được chia sẻ hoặc làm phát sinh thao tác lưu không mong muốn.

**Điều kiện của ví dụ:** các đoạn mã bên dưới dùng Spring Boot 3.x, Java 17 trở lên và Jakarta Persistence. Ứng dụng cần **spring-boot-starter-data-jpa**, JDBC driver, DataSource và schema tương ứng. Đây là các tệp trong ứng dụng Spring Boot, không phải chương trình độc lập có thể chạy chỉ bằng **javac**.

## 1. Cascade là gì?

Giả sử một tác giả có nhiều cuốn sách. Khi tạo tác giả mới và thêm một số sách vào danh sách, ta có thể muốn gọi một lần **persist(author)** để JPA lưu cả tác giả và các sách mới.

Không có cascade:

~~~text
persist(author)
      |
      v
Author được đưa vào persistence context
      |
      +-- Book mới vẫn transient
              |
              +-- Có thể gây lỗi khi flush nếu quan hệ yêu cầu tham chiếu Book chưa được lưu
~~~

Có cascade PERSIST:

~~~text
persist(author)
      |
      v
Author được đưa vào persistence context
      |
      +-- cascade PERSIST
              |
              +-- Book A được persist
              +-- Book B được persist
              +-- Book C được persist
~~~

Cascade được cấu hình trên association. Nó có hướng: thao tác được gọi trên entity nguồn mới lan truyền sang entity đích được tham chiếu. Cascade không tự lan ngược theo chiều association khác.

Ví dụ, nếu cascade được khai báo từ **Author** tới **Book**, gọi persist trên Author có thể lan sang Book. Điều đó không có nghĩa gọi persist trên Book sẽ lan ngược lên Author.

## 2. Sáu kiểu CascadeType chuẩn

| Kiểu | Thao tác được lan truyền | Ý nghĩa |
|---|---|---|
| **PERSIST** | persist | Khi persist entity nguồn, persist các entity đích liên quan |
| **MERGE** | merge | Khi merge entity nguồn, merge các entity đích liên quan |
| **REMOVE** | remove | Khi remove entity nguồn, remove các entity đích liên quan |
| **REFRESH** | refresh | Khi refresh entity nguồn, refresh các entity đích liên quan |
| **DETACH** | detach | Khi detach entity nguồn, detach các entity đích liên quan |
| **ALL** | tất cả các thao tác trên | Tương đương khai báo toàn bộ năm kiểu cascade còn lại |

Ví dụ:

~~~java
@OneToMany(
    mappedBy = "author",
    cascade = {
        CascadeType.PERSIST,
        CascadeType.MERGE
    }
)
private List<Book> books = new ArrayList<>();
~~~

Chỉ **PERSIST** và **MERGE** được lan truyền qua association này. Gọi remove Author không tự động xóa Book chỉ vì association có hai cascade type đó.

**CascadeType.ALL** bao gồm PERSIST, MERGE, REMOVE, REFRESH và DETACH. Nó không phải một kiểu “cascade mọi thứ có thể xảy ra”: JPA không có cascade chuẩn cho truy vấn SELECT, flush hoặc mọi thao tác repository.

## 3. PERSIST: lưu entity mới theo association

**CascadeType.PERSIST** hữu ích khi entity đích có vòng đời phụ thuộc vào entity nguồn và thường được tạo cùng entity nguồn.

Ví dụ Author có nhiều Book:

~~~java
package com.example.catalog.domain;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;

import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "authors")
public class Author {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    @OneToMany(
        mappedBy = "author",
        cascade = CascadeType.PERSIST
    )
    private List<Book> books = new ArrayList<>();

    protected Author() {
    }

    public Author(String name) {
        this.name = name;
    }

    public void addBook(Book book) {
        books.add(book);
        book.assignAuthor(this);
    }

    public Long getId() {
        return id;
    }

    public List<Book> getBooks() {
        return books;
    }
}
~~~

Phía Book:

~~~java
package com.example.catalog.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "books")
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "author_id")
    private Author author;

    protected Book() {
    }

    public Book(String title) {
        this.title = title;
    }

    void assignAuthor(Author author) {
        this.author = author;
    }

    public Long getId() {
        return id;
    }

    public Author getAuthor() {
        return author;
    }
}
~~~

Repository:

~~~java
public interface AuthorRepository extends JpaRepository<Author, Long> {
}
~~~

Service:

~~~java
@Service
public class AuthorService {

    private final AuthorRepository authorRepository;

    public AuthorService(AuthorRepository authorRepository) {
        this.authorRepository = authorRepository;
    }

    @Transactional
    public void registerAuthor() {
        Author author = new Author("Nguyen Van An");
        author.addBook(new Book("Spring Data JPA"));
        author.addBook(new Book("Hibernate in Practice"));

        authorRepository.save(author);
    }
}
~~~

Với entity mới, Spring Data JPA thường gọi persist khi **save(author)** xác định Author là entity mới. JPA thực hiện cascade PERSIST qua danh sách Book, vì vậy các Book mới cũng được persist trong transaction.

### Vì sao phải cập nhật cả hai phía của quan hệ?

Trong ví dụ, **Author.books** khai báo **mappedBy = "author"**, nên đây là inverse side. **Book.author** là owning side vì nó chứa **@JoinColumn** và điều khiển giá trị foreign key **author_id**.

Phương thức **addBook** thêm Book vào collection và đồng thời đặt **book.author = this**. Nếu chỉ thêm vào collection mà không cập nhật owning side, database có thể không nhận được foreign key như mong đợi.

Cascade và owning side là hai khái niệm độc lập:

- Cascade quyết định thao tác vòng đời có được lan truyền không.
- Owning side quyết định phía nào điều khiển cập nhật quan hệ trong database.

## 4. MERGE: đồng bộ trạng thái entity detached

**CascadeType.MERGE** lan truyền thao tác merge từ entity nguồn sang các entity đích.

Merge thường xuất hiện khi ứng dụng nhận một object detached hoặc một graph dữ liệu cần đồng bộ vào persistence context. Với Spring Data JPA, **save(entity)** có thể gọi persist hoặc merge tùy cách xác định entity mới. Nếu thao tác thực tế là merge, cascade MERGE mới lan truyền tới các association được khai báo tương ứng.

Ví dụ:

~~~java
@OneToMany(
    mappedBy = "author",
    cascade = {
        CascadeType.PERSIST,
        CascadeType.MERGE
    }
)
private List<Book> books = new ArrayList<>();
~~~

Khi merge Author, JPA cũng merge các Book liên quan theo cascade MERGE.

Điểm quan trọng của merge là **merge không đơn giản đưa object detached ban đầu trở lại trạng thái managed**. JPA sao chép trạng thái của object nguồn sang một instance managed (có thể là instance khác) và trả về instance managed đó.

Vì vậy, khi gọi EntityManager trực tiếp:

~~~java
Author managedAuthor = entityManager.merge(detachedAuthor);
~~~

hãy tiếp tục làm việc với **managedAuthor**. Không nên giả định **detachedAuthor** đã trở thành managed.

Tương tự, khi dùng Spring Data:

~~~java
Author managedAuthor = authorRepository.save(detachedAuthor);
~~~

nên sử dụng đối tượng được trả về nếu cần tiếp tục thao tác với instance managed. Việc xác định entity mới hay cũ phụ thuộc cơ chế new-state detection của Spring Data, chẳng hạn ID hoặc trường **@Version**.

Không nên dùng MERGE như cách thay thế cho việc thiết kế DTO và quy trình cập nhật rõ ràng. Merge cả một graph detached có thể ghi đè dữ liệu bằng các giá trị null hoặc giá trị cũ nếu object đầu vào không đầy đủ.

## 5. REMOVE: xóa lan truyền và rủi ro

**CascadeType.REMOVE** có nghĩa khi entity nguồn bị remove, các entity đích liên quan cũng nhận thao tác remove.

Ví dụ, nếu Book chỉ tồn tại như một phần của Author và không có vòng đời độc lập, ta có thể cân nhắc cascade REMOVE từ Author tới Book:

~~~java
@OneToMany(
    mappedBy = "author",
    cascade = {
        CascadeType.PERSIST,
        CascadeType.MERGE,
        CascadeType.REMOVE
    }
)
private List<Book> books = new ArrayList<>();
~~~

Khi gọi:

~~~java
authorRepository.deleteById(authorId);
~~~

nếu thao tác được thực hiện thông qua entity lifecycle remove phù hợp, REMOVE cascade có thể lan tới các Book liên quan. SQL cụ thể và thứ tự xóa do provider quản lý; database vẫn phải thỏa foreign key constraints.

### Vì sao REMOVE nguy hiểm ở ManyToOne?

Giả sử nhiều Book cùng tham chiếu một Author:

~~~text
Author A
  ^
  +---- Book 1
  |
  +---- Book 2
  |
  +---- Book 3
~~~

Nếu khai báo **cascade = REMOVE** trên **Book.author**, xóa một Book có thể lan sang xóa Author. Điều đó có thể làm mất tác giả mà các Book khác vẫn đang sử dụng, gây lỗi foreign key hoặc xóa dữ liệu dùng chung.

Thông thường, không nên cascade REMOVE từ phía ManyToOne tới entity được chia sẻ. Hãy chỉ dùng REMOVE khi entity đích thực sự có vòng đời phụ thuộc và không được chia sẻ.

Đặc biệt cẩn trọng với **@ManyToMany**: hai phía thường tham chiếu các entity độc lập và có thể được chia sẻ giữa nhiều bản ghi. Cascade REMOVE trên quan hệ này có thể xóa cả entity dùng chung. Xóa liên kết trong bảng join thường là hành vi mong muốn hơn là xóa entity ở phía bên kia.

## 6. REFRESH: tải lại trạng thái từ database

**CascadeType.REFRESH** lan truyền thao tác refresh tới entity liên quan.

Refresh yêu cầu JPA nạp lại trạng thái entity từ database. Nó hữu ích khi cần loại bỏ trạng thái đang có trong persistence context và đồng bộ với dữ liệu hiện hành trong database.

Ví dụ:

~~~java
@OneToMany(
    mappedBy = "author",
    cascade = CascadeType.REFRESH
)
private List<Book> books = new ArrayList<>();
~~~

Khi gọi:

~~~java
entityManager.refresh(author);
~~~

các Book liên quan cũng được refresh theo cascade.

Cần cẩn thận: refresh có thể ghi đè thay đổi chưa flush trong các entity managed bằng trạng thái hiện tại trong database. Không gọi refresh một cách tùy tiện trên graph đang chứa chỉnh sửa nghiệp vụ chưa được lưu.

REFRESH không có nghĩa là “tải lazy association” nói chung. Nó là một thao tác vòng đời riêng, có thể lan truyền khi được gọi trên entity nguồn.

## 7. DETACH: tách entity khỏi persistence context

**CascadeType.DETACH** lan truyền thao tác detach từ entity nguồn tới các entity đích.

Một entity managed được persistence context theo dõi. Khi detach, entity không còn được theo dõi trong persistence context đó; thay đổi tiếp theo trên object sẽ không tự động được dirty checking ghi xuống database.

Ví dụ:

~~~java
@OneToMany(
    mappedBy = "author",
    cascade = CascadeType.DETACH
)
private List<Book> books = new ArrayList<>();
~~~

Khi gọi:

~~~java
entityManager.detach(author);
~~~

các Book liên quan cũng được detach theo cascade.

DETACH hữu ích trong một số tình huống quản lý persistence context hoặc kiểm soát bộ nhớ, nhưng thường không phải thao tác nghiệp vụ cần gọi trực tiếp. Nếu dùng, hãy hiểu rằng mọi thay đổi chưa flush trên graph có thể không được đồng bộ sau khi entity đã detached.

Đừng nhầm DETACH với REMOVE:

- DETACH chỉ ngừng quản lý object trong persistence context.
- REMOVE đánh dấu entity để xóa khỏi database khi transaction commit.

## 8. CascadeType.ALL có phải lựa chọn mặc định tốt nhất?

**CascadeType.ALL** tương đương:

~~~java
cascade = {
    CascadeType.PERSIST,
    CascadeType.MERGE,
    CascadeType.REMOVE,
    CascadeType.REFRESH,
    CascadeType.DETACH
}
~~~

Nó tiện khi entity đích thực sự có vòng đời hoàn toàn phụ thuộc vào entity nguồn. Nhưng ALL cũng bao gồm REMOVE, REFRESH và DETACH, không chỉ PERSIST/MERGE.

Ví dụ:

~~~java
@OneToMany(
    mappedBy = "author",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<Book> books = new ArrayList<>();
~~~

Cấu hình này có thể phù hợp nếu Book là thành phần thuộc sở hữu của Author và không tồn tại độc lập. Khi xóa Author, Book cũng được xóa; khi bỏ Book khỏi collection, orphan removal sẽ xóa Book đó.

Không nên thêm ALL vào mọi association theo thói quen. Trước khi dùng, hãy trả lời:

- Entity đích có thể được chia sẻ bởi entity khác không?
- Xóa entity nguồn có thực sự phải xóa entity đích không?
- Refresh nguồn có nên ghi đè thay đổi của entity đích không?
- Detach nguồn có nên detach toàn bộ graph không?
- Entity đích có được tạo và cập nhật cùng nguồn không?

Nếu chỉ cần PERSIST và MERGE, hãy khai báo đúng hai thao tác đó. Cấu hình rõ ràng giúp người đọc hiểu vòng đời dữ liệu và giảm rủi ro xóa nhầm.

## 9. CascadeType và orphanRemoval khác nhau

**orphanRemoval = true** là một cơ chế riêng, không phải một giá trị CascadeType. Nó phù hợp với quan hệ **@OneToOne** hoặc **@OneToMany** khi entity con không thể tồn tại độc lập sau khi bị loại khỏi quan hệ cha.

Ví dụ:

~~~java
@OneToMany(
    mappedBy = "author",
    cascade = {
        CascadeType.PERSIST,
        CascadeType.MERGE
    },
    orphanRemoval = true
)
private List<Book> books = new ArrayList<>();
~~~

Nếu một Book bị loại khỏi collection Author.books, JPA sẽ lên lịch xóa orphan đó khi flush theo quy tắc orphan removal.

Phương thức đồng bộ hai phía:

~~~java
public void removeBook(Book book) {
    books.remove(book);
    book.assignAuthor(null);
}
~~~

Với quan hệ bắt buộc, việc bỏ association phải được hiểu là xóa entity con. Orphan removal phù hợp khi Book là thành phần riêng của Author trong mô hình này. Nếu Book có thể được chuyển sang Author khác hoặc được chia sẻ theo nghiệp vụ, cần thiết kế thao tác chuyển quan hệ cẩn thận và thường không nên dùng orphanRemoval.

So sánh:

| Cơ chế | Khi nào kích hoạt | Phạm vi |
|---|---|---|
| **CascadeType.REMOVE** | Khi gọi remove trên entity nguồn | Lan truyền remove tới entity đích được liên kết |
| **orphanRemoval = true** | Khi entity con bị loại khỏi quan hệ cha hoặc cha bị xóa theo semantics JPA | Xóa entity con không còn thuộc cha |
| Database **ON DELETE CASCADE** | Khi database xóa hàng cha có foreign key được cấu hình cascade | Database tự xóa hàng phụ thuộc theo FK |

Ba cơ chế có liên quan nhưng không giống nhau. Cascade JPA là quy tắc ở persistence lifecycle; orphanRemoval mô tả vòng đời entity con; ON DELETE CASCADE là hành vi do database thực thi.

## 10. Cascade có hoạt động với bulk JPQL DELETE/UPDATE không?

Bulk JPQL update/delete thao tác trực tiếp trên database và bỏ qua entity lifecycle thông thường của từng entity trong persistence context. Vì vậy, không nên kỳ vọng cascade JPA, orphanRemoval hoặc entity callback sẽ chạy như khi xóa từng entity bằng EntityManager/repository lifecycle.

Ví dụ:

~~~java
@Modifying
@Query("delete from Book b where b.author.id = :authorId")
int deleteBooksByAuthorId(@Param("authorId") Long authorId);
~~~

Câu lệnh bulk delete này không tương đương với việc tải từng Book rồi gọi remove. Nó không thực hiện cascade REMOVE qua graph entity theo cách thông thường.

Nếu database có foreign key và **ON DELETE CASCADE**, database có thể tự xóa hàng con khi hàng cha bị xóa. Nhưng bulk query xóa Book ở đây là xóa hàng con trực tiếp; quy tắc cascade JPA vẫn không được áp dụng.

Sau bulk update/delete, persistence context có thể giữ entity cũ trong bộ nhớ. Có thể cần clear hoặc refresh phù hợp để tránh đọc trạng thái stale. Spring Data hỗ trợ tùy chọn **clearAutomatically** và **flushAutomatically** trên **@Modifying**, nhưng hãy dùng có chủ đích vì clear có thể detach mọi entity đang được quản lý trong persistence context hiện tại.

## 11. Cascade và transaction là hai trách nhiệm riêng

Cascade quyết định thao tác nào được lan truyền qua association. Transaction quyết định nhóm thao tác có được commit hoặc rollback như một đơn vị.

Ví dụ:

~~~java
@Transactional
public void registerAuthor() {
    Author author = new Author("Nguyen Van An");
    author.addBook(new Book("Spring Data JPA"));

    authorRepository.save(author);
}
~~~

- **@Transactional** mở transaction cho nghiệp vụ.
- **save(author)** yêu cầu Spring Data JPA lưu entity.
- Nếu Author là entity mới, Spring Data thường gọi persist.
- **CascadeType.PERSIST** lan truyền persist tới Book.
- Khi transaction kết thúc thành công, các thay đổi được commit.

Nếu persist cascade xảy ra nhưng transaction sau đó rollback, các thay đổi thuộc transaction đó không được commit. Cascade tự nó không mở transaction và không bảo đảm atomicity.

Với mặc định propagation **REQUIRED**, các repository operations tham gia transaction hiện có của service nếu được gọi trong cùng transaction manager phù hợp. Với nhiều database và transaction manager, cần cấu hình rõ transaction manager mà service sử dụng.

## 12. Kiểm thử cascade

Một bài kiểm thử tích hợp giúp xác nhận hành vi persist cascade:

~~~java
@DataJpaTest
class AuthorCascadeTest {

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private AuthorRepository authorRepository;

    @Test
    void persistsBooksWhenAuthorIsPersisted() {
        Author author = new Author("Nguyen Van An");
        author.addBook(new Book("Spring Data JPA"));

        authorRepository.save(author);
        entityManager.flush();
        entityManager.clear();

        Author loaded = authorRepository.findById(author.getId())
            .orElseThrow();

        assertThat(loaded.getBooks()).hasSize(1);
    }
}
~~~

Test dùng **flush()** để buộc các thay đổi được đồng bộ xuống database và **clear()** để loại entity khỏi persistence context trước khi đọc lại. Nhờ đó, kết quả không chỉ phản ánh collection còn trong bộ nhớ.

Test này giả định **Author.books** có **CascadeType.PERSIST** và cấu hình test có database/schema phù hợp. Nếu collection được tải LAZY, thao tác kiểm tra phải diễn ra trong persistence context test còn hoạt động.

Có thể viết test riêng cho REMOVE hoặc orphanRemoval bằng cách xóa entity/loại child khỏi collection, flush, rồi truy vấn lại bằng một persistence context mới. Đừng chỉ assert collection trong bộ nhớ; hãy xác nhận trạng thái lưu trữ sau flush.

## 13. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Lưu cha nhưng con không được lưu | Thiếu CascadeType.PERSIST hoặc không gọi persist con riêng | Xem xét vòng đời và thêm PERSIST nếu con thuộc sở hữu của cha |
| Cập nhật graph detached không lan tới con | Thiếu CascadeType.MERGE | Thêm MERGE nếu nghiệp vụ thực sự cần merge graph |
| Xóa cha làm mất entity dùng chung | Cascade REMOVE/ALL đặt trên quan hệ chia sẻ | Loại REMOVE và quản lý entity đích độc lập |
| Bỏ child khỏi collection nhưng hàng vẫn còn | Chưa dùng orphanRemoval hoặc chưa gọi remove rõ ràng | Chỉ dùng orphanRemoval khi child có vòng đời phụ thuộc |
| Xóa bằng JPQL nhưng cascade không chạy | Bulk query bỏ qua entity lifecycle | Dùng thao tác entity lifecycle hoặc constraint database phù hợp |
| Association vẫn trỏ sai phía sau khi thêm/xóa | Chỉ cập nhật inverse side | Đồng bộ owning side và inverse side bằng helper methods |
| Merge xong vẫn sửa object cũ | Hiểu nhầm merge là reattach object nguồn | Dùng instance managed được merge trả về |
| Xóa Book làm xóa Author | Cascade REMOVE được khai báo từ ManyToOne | Không cascade remove tới entity được chia sẻ |
| Dữ liệu con bị ghi đè khi refresh | Cascade REFRESH làm mới cả graph | Chỉ refresh khi chấp nhận bỏ thay đổi chưa flush |

## 14. Checklist chọn cascade

- [ ] Xác định entity nào sở hữu vòng đời của entity liên quan.
- [ ] Xác định entity đích có được chia sẻ hoặc tồn tại độc lập không.
- [ ] Dùng **PERSIST** khi lưu entity nguồn cần persist entity con mới.
- [ ] Dùng **MERGE** khi cập nhật graph detached theo nghiệp vụ.
- [ ] Chỉ dùng **REMOVE** khi xóa nguồn thực sự phải xóa entity đích.
- [ ] Dùng **REFRESH** và **DETACH** khi hiểu rõ ảnh hưởng lên trạng thái trong persistence context.
- [ ] Chỉ dùng **ALL** khi mọi thao tác vòng đời đều nên lan truyền.
- [ ] Phân biệt cascade với owning side và mappedBy.
- [ ] Chỉ dùng orphanRemoval cho child có vòng đời phụ thuộc.
- [ ] Không nhầm cascade JPA với ON DELETE CASCADE của database.
- [ ] Không kỳ vọng bulk JPQL update/delete kích hoạt cascade entity lifecycle.
- [ ] Có integration test cho các thao tác persist, merge, remove cần thiết.

## 15. Kết luận

**CascadeType** xác định thao tác vòng đời JPA nào được lan truyền từ entity nguồn sang entity liên quan. PERSIST và MERGE thường hữu ích cho aggregate có vòng đời gắn kết; REMOVE cần thận trọng vì có thể xóa dữ liệu được chia sẻ; REFRESH và DETACH ảnh hưởng trực tiếp tới trạng thái của persistence context; ALL bao gồm toàn bộ các thao tác này.

Hãy chọn cascade theo quan hệ sở hữu và vòng đời nghiệp vụ thực tế. Giữ owning side đúng, dùng orphanRemoval khi child thực sự phụ thuộc vào parent, và nhớ rằng cascade không thay thế transaction hay constraint của database.