# Kiểm tra hướng phụ thuộc và khả năng thay đổi độc lập

Trong module **MODEL_VIEW_CONTROLLER**, việc tách Model, View và Controller giúp tổ chức trạng thái, nghiệp vụ và tương tác giao diện. Tuy nhiên, chỉ chia mã thành ba package hoặc ba nhóm lớp chưa bảo đảm kiến trúc có ranh giới tốt. Một Controller có thể phụ thuộc trực tiếp vào JPA repository, View có thể đọc entity và gọi dịch vụ, còn Model có thể import lớp HTTP hoặc annotation của framework. Khi đó, các thành phần vẫn bị buộc chặt dù tên lớp có vẻ đúng MVC.

Một thiết kế dễ thay đổi cần kiểm tra **hướng phụ thuộc**: lớp nào được phép biết lớp nào, và những hợp đồng nào nằm ở ranh giới giữa chúng. Nó cũng cần kiểm tra **khả năng thay đổi độc lập**: khi thay template, database, giao thức API hoặc một chính sách nghiệp vụ, phạm vi mã phải sửa có được giới hạn hợp lý hay không.

Bài này dùng ví dụ quản lý sách để phân tích phụ thuộc lúc biên dịch, luồng gọi lúc chạy, Dependency Inversion, Ports and Adapters, DTO, kiểm thử theo ranh giới và các dấu hiệu kiến trúc cần xem xét trong một ứng dụng MVC.

## 1. Phân biệt luồng chạy và hướng phụ thuộc mã nguồn

Trong một request web, luồng thực thi thường đi từ ngoài vào trong:

~~~mermaid
flowchart LR
    B[Browser] --> C[Controller]
    C --> A[Application Use Case]
    A --> D[Domain Model]
    A --> P[Repository Port]
    P --> R[Persistence Adapter]
    R --> DB[(Database)]
    A --> C
    C --> V[View / Response]
    V --> B
~~~

Sơ đồ trên mô tả **luồng điều khiển khi chạy**: trình duyệt gửi request, Controller gọi use case, use case làm việc với Model và truy cập dữ liệu, sau đó kết quả quay lại để View tạo response.

Hướng phụ thuộc mã nguồn là câu hỏi khác: lớp nào import hoặc tham chiếu kiểu dữ liệu của lớp nào? Nếu application service gọi một interface repository do chính tầng application định nghĩa, còn adapter persistence triển khai interface đó, hướng phụ thuộc mã nguồn có thể hướng vào trong dù lúc chạy lời gọi đi ra database.

~~~mermaid
flowchart TB
    WEB[Web Adapter<br/>Controller + Form]
    APP[Application Service]
    IN[Input Port]
    OUT[Repository Port]
    DOMAIN[Domain Model]
    INFRA[Persistence Adapter<br/>JPA + Database]
    WEB --> IN
    APP -. implements .-> IN
    APP --> DOMAIN
    APP --> OUT
    INFRA -. implements .-> OUT
~~~

Trong sơ đồ phụ thuộc, mũi tên biểu thị mã nguồn cần biết hợp đồng hoặc kiểu của thành phần ở đầu mũi tên. Application không nên phụ thuộc vào một lớp JPA cụ thể; adapter persistence phụ thuộc vào port mà nó triển khai. Domain nằm ở lõi và không cần biết Spring MVC, template engine hoặc database.

Không được suy luận hướng phụ thuộc chỉ từ thứ tự gọi hàm. Hãy kiểm tra import, constructor parameter, field type, annotation và module dependency thực tế.

## 2. Mục tiêu của hướng phụ thuộc trong MVC

Một cách phân lớp thường dùng:

| Lớp | Trách nhiệm | Nên phụ thuộc vào |
| --- | --- | --- |
| View | Render dữ liệu và chuyển tương tác | Hợp đồng dữ liệu dành cho trình bày |
| Controller / Web Adapter | Nhận HTTP, binding, xác thực request ở ranh giới và tạo response | Application input port, request/response DTO |
| Application | Điều phối use case, transaction và các cổng cần thiết | Domain và các port |
| Domain | Bảo vệ quy tắc, trạng thái và bất biến nghiệp vụ | Kiểu miền cốt lõi; tránh phụ thuộc framework/hạ tầng |
| Infrastructure Adapter | Kết nối database, message broker hoặc dịch vụ ngoài | Port cần triển khai và thư viện kỹ thuật |

Đây không phải luật yêu cầu mọi dự án phải có đúng năm module. Ứng dụng nhỏ có thể dùng ít package hơn. Điều quan trọng là không để chi tiết bên ngoài quyết định cấu trúc và chính sách bên trong.

Ví dụ, quy tắc “không được mượn đầu sách đã lưu trữ” phải tiếp tục đúng khi thao tác đến từ trang HTML, REST API, tác vụ nền hoặc ứng dụng di động. Vì vậy, quy tắc này phải được bảo vệ ở domain/use case phía server, không chỉ trong template.

## 3. Ví dụ phụ thuộc chặt: Controller biết quá nhiều chi tiết

Một Controller có thể gọi thẳng Spring Data repository và dùng entity persistence trong response:

~~~java
@Controller
@RequestMapping("/books")
public class BookController {
    private final SpringDataBookRepository repository;

    public BookController(SpringDataBookRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/{id}")
    public String detail(@PathVariable Long id, Model model) {
        BookJpaEntity book = repository.findById(id).orElseThrow();
        model.addAttribute("book", book);
        return "books/detail";
    }
}
~~~

Đoạn mã đơn giản nhưng Controller đang phụ thuộc vào Spring Data và cấu trúc entity lưu trữ. Template cũng có thể bắt đầu dùng trực tiếp tên thuộc tính persistence. Nếu đổi ORM, schema hoặc cách lưu trữ, nhiều lớp web có thể phải sửa theo.

Một biến thể khác là domain model phụ thuộc framework:

~~~java
@Entity
public class Book {
    @Id
    private Long id;

    @Column(nullable = false)
    private String title;
}
~~~

Đây là lựa chọn thực dụng có thể chấp nhận trong một số ứng dụng Spring/JPA. Tuy nhiên, nó tạo phụ thuộc compile-time từ domain class sang persistence API. Nếu mục tiêu là domain độc lập với hạ tầng, nên tách domain object khỏi JPA entity. Không cần tách máy móc khi chi phí không tương xứng; cần ghi nhận đây là một đánh đổi kiến trúc có chủ đích.

## 4. Dependency Inversion: phụ thuộc vào hợp đồng

Dependency Inversion Principle (DIP) khuyến khích các chính sách cấp cao và chi tiết cấp thấp cùng phụ thuộc vào abstraction ổn định. Chi tiết hạ tầng triển khai abstraction đó, thay vì buộc nghiệp vụ phụ thuộc trực tiếp vào một công nghệ cụ thể.

Trong ví dụ quản lý sách:

- Use case cần khả năng tìm và lưu sách.
- Application định nghĩa port mô tả khả năng đó.
- Adapter JPA triển khai port bằng Spring Data và database.
- Controller gọi input port của use case, không gọi repository persistence.

~~~mermaid
flowchart TB
    CTRL[BookController] --> IN[CreateBookUseCase]
    SVC[CreateBookService] -. implements .-> IN
    SVC --> OUT[BookRepository Port]
    SVC --> DOM[Book Domain]
    JPA[JpaBookRepository Adapter] -. implements .-> OUT
    JPA --> SPRING[Spring Data JPA]
    SPRING --> DB[(Database)]
~~~

Mũi tên nét đứt thể hiện lớp triển khai port tương ứng: application service triển khai input port, còn persistence adapter triển khai output port. Application service gọi output port trong lúc chạy; dependency injection cung cấp implementation phù hợp khi ứng dụng khởi động.

## 5. Thiết kế input port cho use case

Controller chỉ cần biết hợp đồng tạo sách:

~~~java
public record CreateBookCommand(
        String isbn,
        String title,
        String author
) {}

public interface CreateBookUseCase {
    BookId execute(CreateBookCommand command);
}
~~~

Input port biểu diễn một hành động của ứng dụng. Nó không chứa HttpServletRequest, Model của Spring MVC, tên template hoặc kiểu JPA.

Application service triển khai use case:

~~~java
public class CreateBookService implements CreateBookUseCase {
    private final BookRepository books;

    public CreateBookService(BookRepository books) {
        this.books = books;
    }

    @Override
    public BookId execute(CreateBookCommand command) {
        Isbn isbn = Isbn.of(command.isbn());
        if (books.existsByIsbn(isbn)) {
            throw new DuplicateBookIsbnException(isbn);
        }

        Book book = Book.create(
                isbn,
                BookTitle.of(command.title()),
                AuthorName.of(command.author())
        );
        return books.save(book).id();
    }
}
~~~

Ví dụ lược bỏ một số chi tiết về transaction và xử lý cạnh tranh. Nếu ISBN phải duy nhất, database vẫn cần unique constraint để bảo vệ trước hai request đồng thời; kiểm tra exists trước khi save không thay thế được ràng buộc ở database.

Domain model bảo vệ dữ liệu hợp lệ:

~~~java
public final class Book {
    private final BookId id;
    private final Isbn isbn;
    private BookTitle title;
    private AuthorName author;
    private BookStatus status;

    private Book(
            BookId id,
            Isbn isbn,
            BookTitle title,
            AuthorName author,
            BookStatus status) {
        this.id = id;
        this.isbn = isbn;
        this.title = title;
        this.author = author;
        this.status = status;
    }

    public static Book create(
            Isbn isbn,
            BookTitle title,
            AuthorName author) {
        return new Book(
                BookId.newId(),
                isbn,
                title,
                author,
                BookStatus.ACTIVE
        );
    }

    public void archive() {
        if (status == BookStatus.ARCHIVED) {
            throw new BookAlreadyArchivedException(id);
        }
        status = BookStatus.ARCHIVED;
    }

    public BookId id() { return id; }
    public Isbn isbn() { return isbn; }
    public BookTitle title() { return title; }
    public AuthorName author() { return author; }
}
~~~

Domain không cần biết request đến từ form HTML hay JSON. Nó chỉ bảo vệ các điều kiện của đầu sách.

## 6. Định nghĩa output port và adapter persistence

Application định nghĩa repository port theo ngôn ngữ nghiệp vụ:

~~~java
public interface BookRepository {
    boolean existsByIsbn(Isbn isbn);
    Book save(Book book);
    Optional<Book> findById(BookId id);
}
~~~

Adapter persistence triển khai port. Adapter có thể dùng một entity riêng phù hợp schema:

~~~java
@Entity
@Table(name = "books")
public class BookJpaEntity {
    @Id
    private UUID id;
    private String isbn;
    private String title;
    private String author;
    private String status;
}
~~~

~~~java
public interface SpringDataBookRepository
        extends JpaRepository<BookJpaEntity, UUID> {
    boolean existsByIsbn(String isbn);
}
~~~

~~~java
@Repository
public class JpaBookRepositoryAdapter implements BookRepository {
    private final SpringDataBookRepository jpa;
    private final BookPersistenceMapper mapper;

    public JpaBookRepositoryAdapter(
            SpringDataBookRepository jpa,
            BookPersistenceMapper mapper) {
        this.jpa = jpa;
        this.mapper = mapper;
    }

    @Override
    public boolean existsByIsbn(Isbn isbn) {
        return jpa.existsByIsbn(isbn.value());
    }

    @Override
    public Book save(Book book) {
        BookJpaEntity entity = mapper.toEntity(book);
        return mapper.toDomain(jpa.save(entity));
    }

    @Override
    public Optional<Book> findById(BookId id) {
        return jpa.findById(id.value()).map(mapper::toDomain);
    }
}
~~~

Adapter biết JPA entity và Spring Data. Application chỉ biết BookRepository. Khi thay database hoặc ORM, phần cần thay chủ yếu nằm trong adapter và mapper, miễn là hợp đồng nghiệp vụ vẫn phù hợp.

Trong dự án dùng JPA entity làm domain model, có thể không cần mapper hai chiều như ví dụ. Đổi lại, domain sẽ phụ thuộc persistence API. Review cần đánh giá lợi ích và chi phí cụ thể, không xem một cách tổ chức là đúng cho mọi quy mô.

## 7. Web Adapter phụ thuộc vào input port, không phụ thuộc persistence

Controller nhận form, chuyển thành command và gọi use case:

~~~java
public record BookForm(
        @NotBlank String isbn,
        @NotBlank @Size(max = 200) String title,
        @NotBlank @Size(max = 120) String author
) {}
~~~

~~~java
@Controller
@RequestMapping("/books")
public class BookController {
    private final CreateBookUseCase createBook;

    public BookController(CreateBookUseCase createBook) {
        this.createBook = createBook;
    }

    @PostMapping
    public String create(
            @Valid @ModelAttribute("form") BookForm form,
            BindingResult result,
            RedirectAttributes flash) {
        if (result.hasErrors()) {
            return "books/new";
        }

        BookId id = createBook.execute(
                new CreateBookCommand(
                        form.isbn(),
                        form.title(),
                        form.author()
                )
        );
        flash.addFlashAttribute("message", "Đã tạo đầu sách.");
        return "redirect:/books/" + id.value();
    }
}
~~~

Controller phụ thuộc vào input port và command của application. Nó không cần import SpringDataBookRepository hoặc BookJpaEntity. Cấu hình dependency injection ở composition root sẽ nối CreateBookUseCase với CreateBookService và BookRepository với JpaBookRepositoryAdapter.

Nếu có REST API, adapter mới có thể dùng cùng input port nhưng nhận JSON và trả response DTO riêng. Quy tắc tạo sách không phải viết lại trong controller thứ hai.

## 8. DTO là hợp đồng ở ranh giới, không phải bản sao của mọi lớp

DTO giúp tránh để kiểu dữ liệu của một tầng rò sang tầng khác. Tuy nhiên, không cần tạo DTO mới cho mọi lời gọi nội bộ. Hãy tạo hợp đồng khi nó bảo vệ một ranh giới có ý nghĩa:

| Hợp đồng | Ai sử dụng | Mục đích |
| --- | --- | --- |
| BookForm | Web Adapter | Binding và validation dữ liệu form |
| CreateBookCommand | Input port/application | Mô tả yêu cầu tạo sách |
| Book domain object | Domain/application | Bảo vệ trạng thái và hành vi nghiệp vụ |
| BookJpaEntity | Persistence adapter | Ánh xạ schema và quan hệ database |
| BookDetailResponse | REST Adapter | Ổn định JSON contract cho API |
| BookDetailView | Web presentation | Cung cấp đúng dữ liệu cần render template |

Không nên trả JPA entity trực tiếp từ API hoặc đưa HttpServletRequest vào domain. Cũng không nên dùng một DTO khổng lồ làm cả request, command, persistence object và response nếu các vai trò đó có quy tắc khác nhau.

DTO là một phần của hợp đồng. Khi đổi tên hoặc bỏ field, các caller có thể bị ảnh hưởng. Vì vậy, hãy chỉ công khai dữ liệu cần thiết và cân nhắc tương thích ngược cho API bên ngoài.

## 9. Đánh giá khả năng thay đổi độc lập bằng kịch bản

Một thiết kế tốt cho phép thay đổi một chi tiết mà không làm lan rộng thay đổi sang các chính sách không liên quan. Có thể review bằng các kịch bản:

| Kịch bản thay đổi | Phần thường cần thay | Phần nên giữ ổn định |
| --- | --- | --- |
| Đổi Thymeleaf sang một template engine khác | Web View, Controller adapter hoặc mapper trình bày | Domain và use case |
| Thêm REST API bên cạnh HTML | Thêm input adapter và response DTO | Use case/domain hiện có |
| Đổi PostgreSQL sang một database khác | Persistence adapter, mapping, migration và cấu hình | Domain và input port |
| Đổi JPA sang JDBC | Persistence adapter và test tích hợp | Hợp đồng repository nếu semantics không đổi |
| Thay quy tắc lưu trữ đầu sách | Domain policy/use case và test nghiệp vụ | Controller/View nếu contract không đổi |
| Đổi URL hoặc HTTP response | Web adapter và test web | Domain |
| Đổi cách gửi thông báo | Adapter tích hợp và cấu hình | Quy tắc nghiệp vụ, trừ khi semantics use case đổi |

Đây là mục tiêu hướng tới, không phải cam kết rằng một thay đổi chỉ bao giờ chạm một file. Nếu thay đổi làm đổi ý nghĩa nghiệp vụ hoặc public contract, các tầng liên quan cần được cập nhật. Điều cần tránh là đổi database lại buộc phải sửa template, hoặc đổi CSS lại buộc phải sửa domain.

## 10. Dấu hiệu phụ thuộc ngược chiều hoặc rò rỉ hạ tầng

Trong một buổi design review, hãy tìm các dấu hiệu sau:

- Domain import package Spring MVC, Servlet, Thymeleaf hoặc Spring Data.
- Application service nhận HttpServletRequest, Model, ResponseEntity hoặc JPA repository cụ thể.
- Controller tự tạo query persistence hoặc phụ thuộc entity graph.
- View gọi service nghiệp vụ hoặc truy cập repository trực tiếp.
- DTO công khai chứa kiểu nội bộ như Hibernate proxy hoặc entity persistence.
- Domain cần khởi tạo Spring context mới chạy được unit test.
- Thay một framework buộc sửa các lớp nghiệp vụ không liên quan.
- Các package phụ thuộc vòng tròn, ví dụ domain import application và application lại import domain qua lớp triển khai.
- Module web và persistence cùng phụ thuộc trực tiếp vào nhau.
- Interface được đặt ở adapter chỉ để application phải import ngược adapter đó.

Một số annotation không tự động làm kiến trúc sai. Ví dụ, dùng @Transactional ở application service là một đánh đổi phổ biến trong Spring. Nếu cần domain thuần framework, có thể đặt transaction ở decorator hoặc adapter. Review cần xác định phụ thuộc nào là có chủ đích, phụ thuộc nào khiến chính sách cốt lõi bị khóa vào chi tiết.

## 11. Package và module boundary cần phản ánh hướng phụ thuộc

Một cấu trúc package minh họa:

~~~text
book/
  domain/
    Book.java
    BookId.java
    Isbn.java
    BookStatus.java
    BookPolicy.java
  application/
    port/
      in/
        CreateBookUseCase.java
        CreateBookCommand.java
      out/
        BookRepository.java
    service/
      CreateBookService.java
  adapter/
    in/
      web/
        BookController.java
        BookForm.java
        BookDetailView.java
      api/
        BookRestController.java
        BookDetailResponse.java
    out/
      persistence/
        BookJpaEntity.java
        SpringDataBookRepository.java
        JpaBookRepositoryAdapter.java
        BookPersistenceMapper.java
~~~

Package chỉ là cách tổ chức mã nguồn. Nếu toàn bộ package vẫn nằm trong một module và mọi lớp đều public, quy tắc phụ thuộc có thể bị vi phạm mà compiler không ngăn được. Với hệ thống lớn, có thể dùng Java module, Gradle/Maven module hoặc công cụ kiểm tra kiến trúc để giới hạn dependency.

Không nên tách thành nhiều build module chỉ vì sơ đồ có nhiều ô. Module boundary có chi phí cấu hình, build và quản lý version. Bắt đầu bằng package rõ ràng, sau đó tách module khi có nhu cầu độc lập về ownership, build, triển khai hoặc kiểm soát dependency.

## 12. Kiểm tra dependency cycle

Một dependency cycle xuất hiện khi A phụ thuộc B và B phụ thuộc ngược lại A, trực tiếp hoặc qua một chuỗi package khác. Ví dụ:

~~~mermaid
flowchart LR
    WEB[web] --> APP[application]
    APP --> DOMAIN[domain]
    DOMAIN --> WEB
~~~

Trong ví dụ sai, domain phụ thuộc web, làm lõi nghiệp vụ biết cách nhận request. Nếu domain cần một dữ liệu mà web đang sở hữu, hãy chuyển kiểu dữ liệu phù hợp vào domain/application hoặc định nghĩa một port ở phía cần abstraction.

Một chu trình khác có thể xuất hiện khi application service gọi adapter cụ thể, còn adapter import service để gọi ngược callback. Hãy xem có thể thay callback bằng event, port hoặc orchestration ở application hay không.

Không phải mọi vòng gọi lúc chạy đều là dependency cycle. Hai đối tượng có thể gọi nhau qua interface trong một quy trình, nhưng vòng phụ thuộc mã nguồn mới là điều cần phát hiện khi phân tích module và import.

## 13. Kiểm thử độc lập là bằng chứng của ranh giới

Khả năng kiểm thử không phải thước đo duy nhất của kiến trúc, nhưng là một cách hữu ích để xem các lớp có phụ thuộc quá nhiều hay không.

### Domain unit test

Domain test không cần Spring context, database hoặc HTTP:

~~~java
@Test
void archivedBookCannotBeBorrowed() {
    Book book = BookFixture.archived();

    assertThrows(
            BookNotBorrowableException.class,
            book::ensureBorrowable
    );
}
~~~

Nếu chỉ kiểm tra một bất biến đơn giản mà phải khởi động toàn bộ ứng dụng, hãy xem domain có phụ thuộc framework hoặc persistence quá sâu không.

### Application use case test

Có thể thay repository port bằng fake:

~~~java
final class InMemoryBookRepository implements BookRepository {
    private final Map<BookId, Book> data = new HashMap<>();

    @Override
    public boolean existsByIsbn(Isbn isbn) {
        return data.values().stream()
                .anyMatch(book -> book.isbn().equals(isbn));
    }

    @Override
    public Book save(Book book) {
        data.put(book.id(), book);
        return book;
    }

    @Override
    public Optional<Book> findById(BookId id) {
        return Optional.ofNullable(data.get(id));
    }
}
~~~

Use case test có thể xác minh quy tắc trùng ISBN và hành vi lưu mà không cần database thật. Fake cần mô phỏng đúng semantics quan trọng của port; nó không thay thế integration test cho truy vấn và transaction.

### Web adapter test

Controller test có thể mock input port để kiểm tra route, binding, redirect và response. Nếu test cần khởi tạo toàn bộ persistence stack chỉ để xác minh một redirect, ranh giới test có thể đang quá rộng.

### Persistence integration test

Adapter test dùng database phù hợp để xác minh mapping, constraint, query và transaction. Đây là nơi nên kiểm tra hành vi đặc thù của JPA/SQL.

## 14. Kiểm tra kiến trúc tự động

Với codebase lớn, review thủ công không đủ để phát hiện mọi import sai. Có thể dùng ArchUnit để đặt quy tắc package:

~~~java
@AnalyzeClasses(packages = "com.example.book")
class BookArchitectureTest {

    @ArchTest
    static final ArchRule domainMustNotDependOnWeb =
            noClasses()
                    .that().resideInAPackage("..domain..")
                    .should().dependOnClassesThat()
                    .resideInAnyPackage(
                            "org.springframework.web..",
                            "jakarta.servlet..",
                            "org.thymeleaf.."
                    );

    @ArchTest
    static final ArchRule webMustNotDependOnPersistence =
            noClasses()
                    .that().resideInAPackage("..adapter.in.web..")
                    .should().dependOnClassesThat()
                    .resideInAPackage("..adapter.out.persistence..");
}
~~~

Quy tắc cụ thể cần khớp package thật của dự án. Có thể bổ sung kiểm tra dependency cycle, layer access và naming convention. Công cụ tự động giúp ngăn hồi quy nhưng không thể tự quyết định ranh giới nào có ý nghĩa nghiệp vụ; kiến trúc vẫn cần review của nhóm.

## 15. Đánh giá thay đổi hợp đồng

Tách adapter không có nghĩa mọi thay đổi đều hoàn toàn độc lập. Input port và output port là hợp đồng. Nếu hợp đồng đổi, cả caller lẫn implementation có thể cần thay đổi.

Khi review một thay đổi contract, hãy hỏi:

- Hợp đồng mô tả hành động nghiệp vụ hay chi tiết HTTP/database?
- Tên và kiểu dữ liệu có ổn định với các caller khác nhau không?
- Có để lộ entity hoặc kiểu framework ra ngoài adapter không?
- Có thể thêm field tùy chọn mà không phá caller cũ không?
- Thay đổi có làm thay đổi ý nghĩa hành động hay chỉ bổ sung dữ liệu?
- API công khai có cần versioning hoặc giai đoạn tương thích không?
- Có cần giữ adapter cũ trong thời gian chuyển đổi không?

Không nên tạo abstraction chỉ để tránh mọi thay đổi. Một interface có một implementation vẫn có ích nếu nó đánh dấu ranh giới mà application cần kiểm soát. Nhưng nếu interface chỉ lặp lại từng method của một lớp cụ thể và không tạo boundary, nó có thể chỉ tăng boilerplate.

## 16. Quy trình design review theo kịch bản thay đổi

Khi đánh giá một thiết kế MVC, có thể thực hiện theo trình tự:

1. **Vẽ luồng request:** từ View/browser qua Controller, use case, Model và adapter.
2. **Vẽ hướng import:** xác định lớp nào tham chiếu kiểu của lớp nào; không dùng luồng gọi thay cho sơ đồ phụ thuộc.
3. **Xác định lõi nghiệp vụ:** tìm nơi chứa bất biến, chính sách và hành vi cần đúng với mọi adapter.
4. **Kiểm tra ranh giới dữ liệu:** xem Form, Command, Domain Object, Persistence Entity và Response DTO có bị dùng lẫn không.
5. **Tìm dependency ngược:** kiểm tra domain/application có import web, database hoặc framework không.
6. **Tìm cycle:** kiểm tra package/module có phụ thuộc vòng tròn hay không.
7. **Thử kịch bản thay đổi:** đổi template, database, giao thức hoặc chính sách và liệt kê các lớp phải sửa.
8. **Đánh giá test boundary:** xác định domain, use case, adapter có thể được test độc lập đến mức nào.
9. **Đề xuất sửa nhỏ nhất:** chuyển interface về phía caller cần abstraction, tách DTO hoặc thay dependency trực tiếp bằng port khi có lợi ích rõ.
10. **Ghi nhận đánh đổi:** nếu giữ framework annotation trong application hoặc dùng JPA entity làm domain, ghi rõ lý do và giới hạn.

Review tốt cần chỉ ra tác động cụ thể. Thay vì nói “Controller đang coupling”, hãy nêu: “BookController import SpringDataBookRepository và BookJpaEntity; nếu thay persistence adapter, Controller và template phải sửa. Có thể để Controller phụ thuộc CreateBookUseCase và trả BookDetailView.”

## 17. Bảng đánh giá mức độ độc lập

Có thể dùng bảng sau trong buổi review:

| Câu hỏi | Tốt | Cần xem xét |
| --- | --- | --- |
| Domain có chạy unit test mà không khởi tạo Spring không? | Có | Không |
| Application gọi repository qua port ổn định không? | Có | Gọi trực tiếp Spring Data/JPA cụ thể |
| Controller có phụ thuộc use case contract không? | Có | Phụ thuộc persistence hoặc entity nội bộ |
| View nhận dữ liệu trình bày rõ ràng không? | Có | Đọc entity graph hoặc gọi service |
| Đổi template có cần sửa domain không? | Không | Có |
| Đổi database có cần sửa Controller/View không? | Không | Có |
| Thêm API mới có thể dùng lại use case không? | Có | Phải sao chép nghiệp vụ |
| Có dependency cycle giữa các layer không? | Không | Có |
| Hợp đồng có phản ánh nhu cầu của caller không? | Có | Lộ kiểu framework hoặc schema |

Không cần đạt “không phụ thuộc” tuyệt đối. Mục tiêu là phụ thuộc có chủ đích vào hợp đồng ổn định và cô lập chi tiết dễ thay đổi.

## 18. Những sai lầm khi áp dụng Dependency Inversion

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Tạo interface cho mọi class | Nhiều lớp chuyển tiếp nhưng không có boundary có ý nghĩa | Tạo port ở nơi có nhu cầu đảo chiều phụ thuộc |
| Đặt port trong adapter triển khai | Application vẫn phải phụ thuộc ngược adapter | Đặt abstraction ở phía caller cần nó |
| Đưa kiểu HTTP vào application command | Use case bị khóa vào web framework | Dùng kiểu dữ liệu application độc lập |
| Trả JPA entity từ Controller | Web phụ thuộc persistence schema | Dùng response/view DTO |
| Đưa mọi logic vào domain chỉ để tránh framework | Domain có thể ôm cả điều phối và I/O | Phân biệt domain policy với application orchestration |
| Tách module quá sớm | Build và cấu hình phức tạp | Bắt đầu bằng package, tách module khi có nhu cầu thật |
| Dùng fake test thay integration test | Không phát hiện lỗi mapping/query/transaction | Giữ test cho adapter với hạ tầng thật |
| Cố làm mọi thay đổi chỉ sửa đúng một lớp | Tạo abstraction quá mức và hợp đồng cứng | Chấp nhận thay đổi lan truyền khi semantics hoặc contract đổi |

## 19. Checklist cuối buổi review

Trước khi chấp nhận thiết kế, hãy xác nhận:

- Hướng phụ thuộc mã nguồn đã được phân biệt với luồng thực thi chưa?
- Domain có tránh phụ thuộc vào View, Controller, HTTP và persistence adapter không?
- Application có điều phối qua port thay vì gọi chi tiết hạ tầng trực tiếp không?
- Adapter có triển khai hợp đồng do phía trong định nghĩa không?
- Controller có giữ vai trò adapter cho request/response không?
- View có nhận DTO phù hợp thay vì truy cập entity hoặc repository không?
- Request DTO, command, domain object, persistence entity và response DTO có được phân biệt khi cần không?
- Có dependency cycle hoặc import ngược layer không?
- Có thể kiểm thử domain/use case mà không cần khởi động toàn bộ ứng dụng không?
- Có integration test cho hành vi đặc thù database và framework không?
- Các kịch bản đổi giao diện, database và quy tắc đã được xem xét chưa?
- Các đánh đổi kiến trúc có được ghi nhận rõ không?

## Kết luận

Kiểm tra hướng phụ thuộc giúp xác định liệu MVC chỉ được chia thành các lớp theo tên gọi hay đã có ranh giới thực sự. Luồng request thường đi từ View đến Controller rồi vào use case và Model, nhưng hướng phụ thuộc mã nguồn nên hướng về các hợp đồng ổn định ở phía trong. Dependency Inversion và Ports and Adapters giúp application không bị khóa vào JPA, HTTP hoặc template engine. Khi kết hợp DTO đúng ranh giới, kiểm thử độc lập và review theo kịch bản thay đổi, nhóm có thể thay giao diện hoặc hạ tầng với phạm vi sửa đổi được kiểm soát, đồng thời giữ quy tắc nghiệp vụ nhất quán.
