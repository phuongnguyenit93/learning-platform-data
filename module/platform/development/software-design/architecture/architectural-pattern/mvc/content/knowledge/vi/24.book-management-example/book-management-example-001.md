# Yêu cầu danh sách, xem chi tiết, tạo mới và sửa thông tin sách

Một ứng dụng quản lý sách là ví dụ phù hợp để thực hành Model–View–Controller (MVC): người dùng xem danh mục, mở thông tin một cuốn sách, tạo bản ghi mới và cập nhật dữ liệu đã có. Các thao tác này có vẻ đơn giản, nhưng vẫn cần xác định rõ dữ liệu, quyền truy cập, validation, cách phản hồi khi lỗi và ranh giới giữa Controller, nghiệp vụ, persistence và View.

Bài học này chuyển bốn nhu cầu trên thành một yêu cầu chức năng có thể triển khai và kiểm thử. Ví dụ sử dụng ứng dụng web Spring MVC với HTML và Thymeleaf. Các nguyên tắc về request, use case, dữ liệu và response cũng áp dụng cho REST API hoặc framework MVC khác.

Phạm vi minh họa là quản lý thông tin thư mục sách. Các nghiệp vụ mượn/trả, quản lý bản sao vật lý, phạt quá hạn, đặt trước và phân bổ kho không nằm trong bốn use case này. Nếu sản phẩm cần những nghiệp vụ đó, chúng nên được mô hình hóa thành các use case và khái niệm riêng.

## 1. Bối cảnh và mục tiêu

Một thư viện hoặc cửa hàng sách cần duy trì danh mục để nhân viên có thể tra cứu và cập nhật thông tin. Danh mục có thể gồm hàng trăm hoặc hàng nghìn đầu sách. Người dùng cần tìm nhanh một cuốn sách theo tên, tác giả hoặc ISBN; nhân viên cần thêm sách mới và sửa thông tin khi phát hiện dữ liệu sai.

Hệ thống cần hỗ trợ bốn khả năng:

1. **Danh sách sách:** xem các sách hiện có, tìm kiếm, lọc và chuyển trang.
2. **Chi tiết sách:** xem đầy đủ thông tin của một sách được chọn.
3. **Tạo sách:** nhập thông tin và lưu một đầu sách mới.
4. **Sửa sách:** mở biểu mẫu có dữ liệu hiện tại, chỉnh sửa và lưu thay đổi.

~~~mermaid
flowchart TD
    L[Danh sách sách] -->|Chọn một sách| D[Chi tiết sách]
    L -->|Thêm sách| N[Biểu mẫu tạo mới]
    D -->|Sửa thông tin| E[Biểu mẫu chỉnh sửa]
    N -->|Dữ liệu hợp lệ| S[Đã lưu sách]
    E -->|Dữ liệu hợp lệ| S
    S --> D
    N -->|Dữ liệu sai| N
    E -->|Dữ liệu sai| E
~~~

Mục tiêu thiết kế là mỗi request được Controller tiếp nhận, application service thực hiện use case, repository truy cập dữ liệu và View trình bày kết quả. Không để template tự truy vấn database hoặc để Controller chứa toàn bộ quy tắc nghiệp vụ.

## 2. Actor, quyền và giả định nghiệp vụ

Để yêu cầu không mơ hồ, cần xác định ai sử dụng từng chức năng. Ví dụ này dùng hai nhóm actor:

| Actor | Xem danh sách/chi tiết | Tạo sách | Sửa sách |
|---|---:|---:|---:|
| Người xem danh mục | Có | Không | Không |
| Nhân viên quản lý sách | Có | Có | Có |

Ứng dụng có thể yêu cầu đăng nhập đối với mọi trang hoặc cho phép khách xem danh mục công khai. Trong bài này, giả định danh mục được phép đọc; thao tác tạo và sửa chỉ dành cho người dùng có quyền BOOK_CATALOG_WRITE.

Một số giả định dữ liệu:

- Mỗi đầu sách có một định danh nội bộ duy nhất.
- ISBN là mã nhận diện sách và phải được chuẩn hóa trước khi kiểm tra trùng.
- Tiêu đề là trường bắt buộc.
- Một sách có ít nhất một tác giả; hệ thống đơn giản có thể lưu tên tác giả dạng văn bản.
- Nhà xuất bản, ngày xuất bản, thể loại và mô tả có thể không bắt buộc.
- Việc sửa thông tin không làm thay đổi lịch sử mượn/trả hoặc số lượng bản sao vật lý.

Các giả định này cần được xác nhận với chủ sản phẩm trước khi triển khai thực tế. Ví dụ, một cuốn sách có nhiều ấn bản có thể cần mô hình Book và Edition riêng; khi đó ISBN thường thuộc về ấn bản thay vì đầu sách tổng quát.

## 3. Yêu cầu chức năng: danh sách sách

Người dùng mở trang danh sách và nhận được các sách đang được quản lý. Mỗi dòng hoặc thẻ sách nên hiển thị đủ thông tin để nhận biết nhanh:

- Tiêu đề.
- Tác giả.
- ISBN nếu có.
- Nhà xuất bản hoặc năm xuất bản nếu có.
- Liên kết đến trang chi tiết.

Danh sách cần hỗ trợ:

- Tìm kiếm theo tiêu đề, tác giả hoặc ISBN.
- Lọc theo thể loại nếu dữ liệu có phân loại.
- Sắp xếp theo tiêu đề, tác giả, ngày xuất bản hoặc thời điểm cập nhật.
- Phân trang để không tải toàn bộ danh mục trong một request.
- Hiển thị trạng thái rỗng khi không có sách phù hợp.

Điều kiện chấp nhận:

1. Khi mở GET /books, hệ thống hiển thị danh sách theo thứ tự mặc định đã thống nhất.
2. Khi nhập từ khóa, kết quả chỉ gồm sách khớp tiêu chí tìm kiếm.
3. Khi không có kết quả, trang hiển thị thông báo phù hợp và vẫn cho phép xóa bộ lọc.
4. Khi chuyển trang, từ khóa và bộ lọc hiện tại được giữ lại.
5. Mỗi sách có liên kết mở đúng trang chi tiết.

## 4. Yêu cầu chức năng: xem chi tiết sách

Người dùng chọn một sách từ danh sách hoặc mở trực tiếp URL chi tiết. Trang chi tiết hiển thị những trường đã được lưu:

- Mã nội bộ hoặc ISBN.
- Tiêu đề.
- Tác giả.
- Nhà xuất bản.
- Ngày hoặc năm xuất bản.
- Thể loại.
- Mô tả.
- Thời điểm tạo và cập nhật nếu cần cho nhân viên quản lý.

Điều kiện chấp nhận:

1. ID hợp lệ và tồn tại thì hiển thị đúng thông tin sách.
2. ID không tồn tại thì trả trang 404 hoặc response 404 theo loại client.
3. Người có quyền sửa thấy hành động sửa; người chỉ có quyền đọc không thấy hành động này.
4. Việc ẩn nút sửa chỉ phục vụ giao diện; server vẫn phải kiểm tra quyền khi nhận request cập nhật.

## 5. Yêu cầu chức năng: tạo sách mới

Nhân viên có quyền mở biểu mẫu tạo sách, nhập thông tin và gửi request lưu.

| Trường | Bắt buộc | Quy tắc |
|---|---:|---|
| ISBN | Theo chính sách danh mục | Định dạng hợp lệ; duy nhất sau chuẩn hóa |
| Tiêu đề | Có | Không rỗng; giới hạn độ dài |
| Tác giả | Có | Ít nhất một tên tác giả |
| Nhà xuất bản | Không | Giới hạn độ dài |
| Ngày xuất bản | Không | Ngày hợp lệ, không ở tương lai nếu chính sách yêu cầu |
| Thể loại | Không | Phải thuộc danh mục thể loại được phép |
| Mô tả | Không | Giới hạn độ dài; hiển thị an toàn |

Điều kiện chấp nhận:

1. Người không có quyền ghi bị từ chối khi mở hoặc gửi biểu mẫu tạo sách.
2. Form hợp lệ tạo đúng một bản ghi mới.
3. ISBN trùng bị từ chối bằng thông báo dễ hiểu.
4. Dữ liệu sai được hiển thị lại cùng lỗi theo trường; dữ liệu đã nhập hợp lệ được giữ lại.
5. Khi tạo thành công, ứng dụng redirect đến trang chi tiết hoặc danh sách và hiển thị thông báo thành công.
6. Refresh trang sau redirect không gửi lại POST vừa thực hiện.

## 6. Yêu cầu chức năng: sửa thông tin sách

Nhân viên mở trang chỉnh sửa từ chi tiết sách. Form được điền bằng dữ liệu hiện tại. Sau khi thay đổi, người dùng gửi form để cập nhật.

Điều kiện chấp nhận:

1. Form chỉnh sửa chỉ mở được khi sách tồn tại và actor có quyền.
2. Các trường hiện tại được điền vào form.
3. Dữ liệu hợp lệ cập nhật đúng sách, không tạo bản ghi mới.
4. ISBN có thể giữ nguyên; nếu thay đổi thì phải kiểm tra trùng với sách khác.
5. Nếu dữ liệu không hợp lệ, form được render lại cùng thông báo lỗi.
6. Nếu sách bị xóa hoặc không còn tồn tại trước lúc cập nhật, ứng dụng trả 404.
7. Nếu người khác cập nhật cùng bản ghi trước đó, ứng dụng xử lý xung đột theo chính sách thay vì âm thầm ghi đè.

## 7. Yêu cầu phi chức năng

| Nhóm | Yêu cầu minh họa |
|---|---|
| Hiệu năng | Danh sách dùng phân trang; query tìm kiếm có giới hạn |
| Bảo mật | Chỉ actor có quyền được tạo/sửa; dùng CSRF protection cho form session-based |
| Toàn vẹn dữ liệu | ISBN duy nhất ở database; dữ liệu bắt buộc được kiểm tra |
| Khả năng sử dụng | Lỗi gắn với trường; form giữ lại dữ liệu đã nhập |
| Khả năng bảo trì | Controller mỏng; use case có thể kiểm thử độc lập |
| Khả năng quan sát | Log lỗi có request ID; không ghi toàn bộ dữ liệu form nhạy cảm |
| Khả năng truy cập | Form có label, thông báo lỗi liên kết với trường và điều hướng bàn phím |

Các con số như thời gian phản hồi, kích thước trang và giới hạn độ dài cần được xác định theo yêu cầu sản phẩm và hạ tầng, không nên tự chọn một giá trị rồi coi đó là chuẩn chung.

## 8. Mô hình dữ liệu sách

Một mô hình đơn giản có thể biểu diễn như sau:

~~~mermaid
erDiagram
    BOOK {
        UUID id PK
        VARCHAR isbn UK
        VARCHAR title
        VARCHAR author
        VARCHAR publisher
        DATE publication_date
        VARCHAR category
        TEXT description
        TIMESTAMP created_at
        TIMESTAMP updated_at
        BIGINT version
    }
~~~

id là khóa nội bộ. isbn có ràng buộc unique sau khi chuẩn hóa. version hỗ trợ optimistic locking nếu ứng dụng cần phát hiện cập nhật đồng thời.

Ví dụ entity rút gọn:

~~~java
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
    @GeneratedValue
    private UUID id;

    @Column(length = 17)
    private String isbn;

    @Column(nullable = false, length = 200)
    private String title;

    @Column(nullable = false, length = 300)
    private String author;

    @Column(length = 160)
    private String publisher;

    private LocalDate publicationDate;

    @Column(length = 80)
    private String category;

    @Column(length = 4000)
    private String description;

    @Version
    private long version;

    protected Book() {
    }

    // Factory và hành vi nghiệp vụ được đặt trong domain model.
}
~~~

Đây là mô hình cho ví dụ một tên tác giả dạng văn bản. Nếu cần nhiều tác giả, tác giả là thực thể được quản lý riêng hoặc cần hỗ trợ nhiều ngôn ngữ, nên thay bằng quan hệ và kiểu dữ liệu phù hợp. Không nên cố mở rộng một cột văn bản thành mô hình quan hệ bằng cách lưu chuỗi phân cách.

### 8.1. Chuẩn hóa ISBN

Người dùng có thể nhập ISBN với dấu gạch nối hoặc khoảng trắng. Trước khi lưu và kiểm tra trùng, ứng dụng nên chuẩn hóa định dạng theo quy tắc đã chọn, ví dụ bỏ dấu phân cách và chuẩn hóa chữ X của ISBN-10 thành chữ hoa.

Chỉ kiểm tra chuỗi có 10 hoặc 13 ký tự là chưa đủ để xác nhận ISBN hợp lệ; ISBN-10 và ISBN-13 có quy tắc checksum riêng. Có thể dùng validator chuyên biệt hoặc thư viện đã được kiểm chứng.

Nếu ISBN là trường tùy chọn, giá trị chỉ gồm khoảng trắng nên được chuẩn hóa thành null trước khi lưu thay vì lưu chuỗi rỗng. Cách database xử lý nhiều giá trị null trong unique constraint có thể khác nhau; cần xác định rõ chính sách theo hệ quản trị đang dùng.

Không chỉ kiểm tra trùng ở application service. Ràng buộc unique tại database là lớp bảo vệ cuối cùng trước hai request đồng thời cùng tạo một ISBN.

## 9. Hợp đồng dữ liệu giữa Form, Application và View

Không nên dùng một entity Book cho mọi vai trò. Tách các kiểu dữ liệu giúp giới hạn trường đầu vào và trường đầu ra.

~~~java
public record BookForm(
        @NotBlank @Size(max = 200) String title,
        @Size(max = 17) String isbn,
        @NotBlank @Size(max = 300) String author,
        @Size(max = 160) String publisher,
        @PastOrPresent LocalDate publicationDate,
        @Size(max = 80) String category,
        @Size(max = 4000) String description,
        Long version
) {
    public static BookForm empty() {
        return new BookForm("", "", "", "", null, "", "", null);
    }
}
~~~

Trong dự án thực tế, validator ISBN và quy tắc ngày xuất bản cần phù hợp với chính sách nghiệp vụ. PastOrPresent chỉ là ví dụ nếu thư viện không chấp nhận ngày xuất bản tương lai; nếu hệ thống quản lý sách sắp phát hành, quy tắc này cần thay đổi.

Application command:

~~~java
public record CreateBookCommand(
        String title,
        String isbn,
        String author,
        String publisher,
        LocalDate publicationDate,
        String category,
        String description
) {}

public record UpdateBookCommand(
        String title,
        String isbn,
        String author,
        String publisher,
        LocalDate publicationDate,
        String category,
        String description,
        Long expectedVersion
) {}
~~~

View DTO:

~~~java
public record BookListItem(
        UUID id,
        String title,
        String author,
        String isbn,
        String publisher
) {}

public record BookDetailView(
        UUID id,
        String title,
        String author,
        String isbn,
        String publisher,
        LocalDate publicationDate,
        String category,
        String description,
        Instant updatedAt,
        Long version
) {}
~~~

Form DTO đại diện dữ liệu người dùng được phép gửi; command biểu diễn ý định nghiệp vụ; View DTO chỉ chứa dữ liệu cần trình bày. Ba kiểu này có thể có một số trường giống nhau nhưng không nên mặc định đồng nhất.

## 10. Ánh xạ bốn use case thành endpoint

Với HTML MVC, có thể dùng các route:

| Use case | Method | URL | Kết quả |
|---|---|---|---|
| Danh sách | GET | /books | Render books/list |
| Chi tiết | GET | /books/{id} | Render books/detail |
| Form tạo | GET | /books/new | Render books/form |
| Lưu sách mới | POST | /books | Validate, tạo, redirect |
| Form sửa | GET | /books/{id}/edit | Render books/form |
| Lưu cập nhật | POST | /books/{id} | Validate, cập nhật, redirect |

Với REST API, có thể dùng GET /api/books, GET /api/books/{id}, POST /api/books và PUT /api/books/{id}. API có thể dùng status 201 Created và header Location khi tạo thành công, 200 OK hoặc 204 No Content khi cập nhật theo hợp đồng đã chọn.

Không nên trộn tùy tiện route HTML và API chỉ vì chúng dùng cùng application service. Adapter web và adapter REST có thể dùng chung use case nhưng có hợp đồng HTTP riêng.

## 11. Luồng xử lý tổng thể theo MVC

Khi nhân viên tạo sách:

~~~mermaid
sequenceDiagram
    actor Staff as Nhân viên
    participant B as Browser
    participant C as BookController
    participant A as BookCommandService
    participant D as Book Domain
    participant R as BookRepository
    participant DB as Database

    Staff->>B: Nhập form sách
    B->>C: POST /books + form data + CSRF
    C->>C: Bind và validate
    C->>A: create(CreateBookCommand)
    A->>R: Kiểm tra ISBN
    R->>DB: Query ISBN
    DB-->>R: Chưa tồn tại
    A->>D: Tạo Book
    A->>R: save(Book)
    R->>DB: INSERT
    DB-->>R: Book ID
    R-->>A: Book
    A-->>C: Book ID
    C-->>B: Redirect /books/{id}
    B->>C: GET /books/{id}
    C-->>B: HTML chi tiết sách
~~~

Luồng thực tế có thể có thêm security filter, exception handler, transaction interceptor và ViewResolver. Sơ đồ tập trung vào trách nhiệm chính của từng tầng.

## 12. Cấu trúc package gợi ý

~~~text
com.example.library/
├── book/
│   ├── web/
│   │   ├── BookController.java
│   │   ├── BookForm.java
│   │   └── BookViewMapper.java
│   ├── application/
│   │   ├── BookQueryService.java
│   │   ├── BookCommandService.java
│   │   ├── CreateBookCommand.java
│   │   └── UpdateBookCommand.java
│   ├── domain/
│   │   ├── Book.java
│   │   └── Isbn.java
│   └── infrastructure/
│       ├── JpaBookRepository.java
│       └── SpringDataBookRepository.java
├── shared/
│   └── web/
│       └── GlobalExceptionHandler.java
└── LibraryApplication.java
~~~

Đây là cấu trúc gợi ý. Dự án nhỏ có thể dùng ít package hơn; dự án lớn có thể chia thêm port, adapter và module boundary. Điều quan trọng là Controller không phụ thuộc trực tiếp vào chi tiết ORM và domain không phụ thuộc Spring MVC.

## 13. Repository cho danh sách và chi tiết

Repository có thể cung cấp các thao tác:

~~~java
public interface BookRepository {
    Page<BookListItem> search(
            String keyword,
            String category,
            Pageable pageable
    );

    Optional<Book> findById(UUID id);

    boolean existsByNormalizedIsbn(String isbn);

    boolean existsByNormalizedIsbnAndIdNot(String isbn, UUID id);

    Book save(Book book);
}
~~~

Đây là application-facing port minh họa. Implementation có thể dùng Spring Data JPA và projection để không tải toàn bộ entity khi chỉ cần dữ liệu danh sách.

Với danh sách, nên phân trang tại database. Không nên tải mọi sách rồi lọc trong Java khi danh mục có thể tăng lớn. Với truy vấn tìm kiếm, cần thống nhất quy tắc không phân biệt hoa/thường, dấu tiếng Việt và cách xử lý khoảng trắng. Hành vi tìm kiếm phụ thuộc database/collation và có thể cần full-text index nếu dữ liệu lớn.

## 14. Application service cho truy vấn

Query service chịu trách nhiệm lấy dữ liệu phù hợp cho danh sách và chi tiết:

~~~java
@Service
public class BookQueryService {
    private final BookRepository bookRepository;

    public BookQueryService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @Transactional(readOnly = true)
    public Page<BookListItem> search(
            String keyword,
            String category,
            Pageable pageable
    ) {
        return bookRepository.search(
                normalizeKeyword(keyword),
                category,
                pageable
        );
    }

    @Transactional(readOnly = true)
    public BookDetailView getDetail(UUID id) {
        Book book = bookRepository.findById(id)
                .orElseThrow(BookNotFoundException::new);
        return BookViewMapper.toDetail(book);
    }
}
~~~

normalizeKeyword có thể trim khoảng trắng và chuẩn hóa chuỗi theo chính sách tìm kiếm. Không nên tự loại dấu tiếng Việt nếu sản phẩm cần phân biệt dấu; quyết định này phải thống nhất với cách database tìm kiếm.

Query service trả DTO thay vì entity để Controller và View không phụ thuộc cấu trúc persistence.

## 15. Application service cho tạo và cập nhật

Command service điều phối thao tác thay đổi dữ liệu:

~~~java
@Service
public class BookCommandService {
    private final BookRepository bookRepository;

    public BookCommandService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @Transactional
    public UUID create(CreateBookCommand command) {
        String isbn = normalizeIsbn(command.isbn());
        ensureIsbnAvailable(isbn, null);

        Book book = Book.create(
                isbn,
                command.title().trim(),
                command.author().trim(),
                command.publisher(),
                command.publicationDate(),
                command.category(),
                command.description()
        );
        return bookRepository.save(book).getId();
    }

    @Transactional
    public void update(UUID id, UpdateBookCommand command) {
        Book book = bookRepository.findById(id)
                .orElseThrow(BookNotFoundException::new);

        if (command.expectedVersion() == null
                || book.getVersion() != command.expectedVersion()) {
            throw new BookVersionConflictException();
        }

        String isbn = normalizeIsbn(command.isbn());
        ensureIsbnAvailable(isbn, id);

        book.updateInformation(
                isbn,
                command.title().trim(),
                command.author().trim(),
                command.publisher(),
                command.publicationDate(),
                command.category(),
                command.description()
        );
        bookRepository.save(book);
    }

    private void ensureIsbnAvailable(String isbn, UUID currentId) {
        if (isbn == null || isbn.isBlank()) {
            return;
        }

        boolean duplicate = currentId == null
                ? bookRepository.existsByNormalizedIsbn(isbn)
                : bookRepository.existsByNormalizedIsbnAndIdNot(isbn, currentId);

        if (duplicate) {
            throw new DuplicateIsbnException();
        }
    }
}
~~~

Đoạn mã minh họa luồng điều phối. Trong dự án thực tế, chuẩn hóa ISBN có thể được đóng gói trong value object; validator cần kiểm tra checksum; database unique constraint vẫn là lớp bảo vệ cuối cùng trước hai request đồng thời cùng tạo một ISBN. Application service cần bắt và ánh xạ lỗi constraint phù hợp thay vì trả stack trace.

Domain object nên bảo vệ quy tắc của chính nó:

~~~java
public void updateInformation(
        String isbn,
        String title,
        String author,
        String publisher,
        LocalDate publicationDate,
        String category,
        String description
) {
    if (title == null || title.isBlank()) {
        throw new InvalidBookTitleException();
    }
    this.isbn = isbn;
    this.title = title;
    this.author = author;
    this.publisher = publisher;
    this.publicationDate = publicationDate;
    this.category = category;
    this.description = description;
}
~~~

Validation annotation ở form cải thiện trải nghiệm nhập liệu; domain vẫn bảo vệ bất biến khi use case được gọi từ adapter khác.

## 16. Controller cho danh sách, chi tiết và biểu mẫu

Controller HTML có thể xử lý các use case đọc và hiển thị form:

~~~java
@Controller
@RequestMapping("/books")
public class BookController {
    private final BookQueryService queryService;
    private final BookCommandService commandService;

    public BookController(
            BookQueryService queryService,
            BookCommandService commandService
    ) {
        this.queryService = queryService;
        this.commandService = commandService;
    }

    @GetMapping
    public String list(
            @RequestParam(required = false) String q,
            @RequestParam(required = false) String category,
            @PageableDefault(size = 20, sort = "title") Pageable pageable,
            Model model
    ) {
        model.addAttribute("page", queryService.search(q, category, pageable));
        model.addAttribute("keyword", q);
        model.addAttribute("category", category);
        return "books/list";
    }

    @GetMapping("/{id}")
    public String detail(@PathVariable UUID id, Model model) {
        model.addAttribute("book", queryService.getDetail(id));
        return "books/detail";
    }

    @GetMapping("/new")
    @PreAuthorize("hasAuthority('BOOK_CATALOG_WRITE')")
    public String newForm(Model model) {
        model.addAttribute("form", BookForm.empty());
        model.addAttribute("bookId", null);
        return "books/form";
    }

    @GetMapping("/{id}/edit")
    @PreAuthorize("hasAuthority('BOOK_CATALOG_WRITE')")
    public String editForm(@PathVariable UUID id, Model model) {
        BookDetailView book = queryService.getDetail(id);
        model.addAttribute("book", book);
        model.addAttribute("form", BookMapper.toForm(book));
        model.addAttribute("bookId", id);
        return "books/form";
    }
}
~~~

Cần giới hạn thuộc tính sắp xếp mà client được phép yêu cầu; không chuyển trực tiếp mọi giá trị sort tùy ý từ query string xuống database. Có thể định nghĩa allowlist như title, author và updatedAt.

## 17. Controller cho tạo và sửa

Hai thao tác ghi có thể được triển khai như sau:

~~~java
@PostMapping
@PreAuthorize("hasAuthority('BOOK_CATALOG_WRITE')")
public String create(
        @Valid @ModelAttribute("form") BookForm form,
        BindingResult errors,
        Model model,
        RedirectAttributes redirect
) {
    if (errors.hasErrors()) {
        model.addAttribute("bookId", null);
        return "books/form";
    }

    UUID id = commandService.create(BookMapper.toCreateCommand(form));
    redirect.addFlashAttribute("notice", "Đã tạo sách.");
    return "redirect:/books/" + id;
}

@PostMapping("/{id}")
@PreAuthorize("hasAuthority('BOOK_CATALOG_WRITE')")
public String update(
        @PathVariable UUID id,
        @Valid @ModelAttribute("form") BookForm form,
        BindingResult errors,
        Model model,
        RedirectAttributes redirect
) {
    if (errors.hasErrors()) {
        model.addAttribute("bookId", id);
        return "books/form";
    }

    commandService.update(id, BookMapper.toUpdateCommand(form));
    redirect.addFlashAttribute("notice", "Đã cập nhật thông tin sách.");
    return "redirect:/books/" + id;
}
~~~

Khi validation lỗi ở form chỉnh sửa, Controller cần cung cấp lại mọi dữ liệu phụ trợ mà template cần, ví dụ bookId và danh sách thể loại. Có thể thiết kế một form view model chứa cả ID và dữ liệu nhập để tránh thiếu model attribute.

Trong Spring Security, method authorization cần được bật, chẳng hạn bằng @EnableMethodSecurity, và cấu hình đúng. CSRF protection cho form session-based vẫn cần được giữ. Việc có annotation ở Controller không thay thế kiểm tra quyền trên bản ghi nếu ứng dụng có phạm vi dữ liệu theo chi nhánh hoặc tenant.

## 18. Thiết kế View danh sách và chi tiết

Template books/list.html nhận page, keyword và category từ Controller:

~~~html
<h1>Danh mục sách</h1>
<form method="get" th:action="@{/books}">
    <label for="q">Tìm sách</label>
    <input id="q" name="q" type="search" th:value="${keyword}">
    <label for="category">Thể loại</label>
    <input id="category" name="category" th:value="${category}">
    <button type="submit">Tìm</button>
    <a th:href="@{/books}">Xóa bộ lọc</a>
</form>

<p th:if="${page.empty}">Không tìm thấy sách phù hợp.</p>
<table th:if="${!page.empty}">
    <thead>
        <tr><th>Tiêu đề</th><th>Tác giả</th><th>ISBN</th></tr>
    </thead>
    <tbody>
        <tr th:each="book : ${page.content}">
            <td>
                <a th:href="@{/books/{id}(id=${book.id})}"
                   th:text="${book.title}">Tên sách</a>
            </td>
            <td th:text="${book.author}">Tác giả</td>
            <td th:text="${book.isbn}">ISBN</td>
        </tr>
    </tbody>
</table>
~~~

th:text escape nội dung theo cơ chế của Thymeleaf. Tránh dùng th:utext cho dữ liệu người dùng nếu chưa có quy trình sanitize đáng tin cậy. Nội dung mô tả hoặc tên sách có thể chứa chuỗi giống HTML; mặc định nên hiển thị như văn bản.

Phần phân trang cần giữ lại bộ lọc hiện tại. Spring Data dùng page index bắt đầu từ 0; giao diện có thể hiển thị số trang bắt đầu từ 1 nhưng query parameter phải dùng index tương ứng.

Template books/detail.html chỉ hiển thị DTO đã được query service chuẩn bị:

~~~html
<article>
    <h1 th:text="${book.title}">Tên sách</h1>
    <dl>
        <dt>Tác giả</dt><dd th:text="${book.author}">Tác giả</dd>
        <dt>ISBN</dt><dd th:text="${book.isbn}">ISBN</dd>
        <dt>Nhà xuất bản</dt><dd th:text="${book.publisher}">Nhà xuất bản</dd>
        <dt>Ngày xuất bản</dt><dd th:text="${book.publicationDate}">Ngày</dd>
        <dt>Thể loại</dt><dd th:text="${book.category}">Thể loại</dd>
    </dl>
    <p th:text="${book.description}">Mô tả sách</p>
    <a th:href="@{/books}">Quay lại danh sách</a>
    <a th:if="${canEdit}"
       th:href="@{/books/{id}/edit(id=${book.id})}">Sửa thông tin</a>
</article>
~~~

canEdit chỉ điều khiển hiển thị nút theo quyền hiện tại. Security filter hoặc method authorization vẫn phải kiểm tra quyền ở các route tạo và cập nhật.

## 19. Dùng chung form cho tạo mới và chỉnh sửa

Hai màn hình có các trường gần giống nhau, vì vậy có thể dùng chung template books/form.html. Controller cung cấp form và bookId; bookId có giá trị khi chỉnh sửa, rỗng khi tạo mới.

~~~html
<h1 th:text="${bookId == null ? 'Thêm sách' : 'Sửa thông tin sách'}">
    Thêm sách
</h1>

<form method="post"
      th:object="${form}"
      th:action="${bookId == null ? '/books' : '/books/' + bookId}">
    <label for="title">Tiêu đề</label>
    <input id="title" type="text" th:field="*{title}">
    <p th:if="${#fields.hasErrors('title')}" th:errors="*{title}">Lỗi tiêu đề</p>

    <label for="isbn">ISBN</label>
    <input id="isbn" type="text" th:field="*{isbn}">
    <p th:if="${#fields.hasErrors('isbn')}" th:errors="*{isbn}">Lỗi ISBN</p>

    <label for="author">Tác giả</label>
    <input id="author" type="text" th:field="*{author}">
    <p th:if="${#fields.hasErrors('author')}" th:errors="*{author}">Lỗi tác giả</p>

    <label for="publisher">Nhà xuất bản</label>
    <input id="publisher" type="text" th:field="*{publisher}">
    <label for="publicationDate">Ngày xuất bản</label>
    <input id="publicationDate" type="date" th:field="*{publicationDate}">
    <label for="category">Thể loại</label>
    <input id="category" type="text" th:field="*{category}">
    <label for="description">Mô tả</label>
    <textarea id="description" th:field="*{description}"></textarea>
    <input type="hidden" th:field="*{version}">
    <button type="submit">Lưu</button>
</form>
~~~

Thymeleaf và Spring Security integration có thể tự thêm CSRF hidden input khi cấu hình phù hợp. Nếu không, cần thêm token CSRF theo cách framework yêu cầu. Không tắt CSRF chỉ để form POST hoạt động trong quá trình phát triển.

Khi validation lỗi ở form chỉnh sửa, Controller phải cung cấp lại bookId và mọi dữ liệu phụ trợ mà template cần. Form cần có label rõ ràng, thông báo lỗi liên kết với trường và trạng thái focus dễ nhận biết.

## 20. Validation ở nhiều lớp

Validation không chỉ là một annotation trên form. Nên phân biệt:

| Lớp | Ví dụ | Mục đích |
|---|---|---|
| Form/Request DTO | Tiêu đề không rỗng, giới hạn độ dài | Phản hồi lỗi nhập liệu sớm |
| Application | Actor có quyền, ISBN chưa thuộc sách khác | Bảo vệ use case |
| Domain | Tiêu đề hợp lệ, quy tắc cập nhật | Bảo vệ bất biến |
| Database | NOT NULL, UNIQUE, foreign key | Bảo vệ toàn vẹn trước race condition |

Một ISBN có thể không trùng ở thời điểm query nhưng hai request đồng thời vẫn cùng vượt qua kiểm tra. Unique constraint của database ngăn hai bản ghi cùng lưu. Application service cần bắt lỗi constraint phù hợp và chuyển thành lỗi nghiệp vụ có thể hiển thị, thay vì trả stack trace.

Với thể loại, không nên chỉ nhận chuỗi tùy ý nếu hệ thống có danh mục chuẩn. Dùng category ID hoặc slug và xác minh thể loại tồn tại, đang hoạt động và được phép chọn.

## 21. Xử lý lỗi và status

| Tình huống | HTML MVC | REST API |
|---|---|---|
| Không tìm thấy sách | Trang 404 | 404 Not Found |
| Form sai | Render lại form và lỗi | 400 Bad Request |
| ISBN trùng | Render form với lỗi ISBN | 409 Conflict hoặc 400 theo hợp đồng |
| Chưa đăng nhập | Redirect login | 401 Unauthorized |
| Đã đăng nhập nhưng thiếu quyền | 403 hoặc 404 theo chính sách | 403 hoặc 404 |
| Cập nhật xung đột phiên bản | Trang thông báo xung đột | 409 Conflict |
| Lỗi hệ thống không dự kiến | Trang lỗi chung có mã hỗ trợ | 500 với error response an toàn |

Không hiển thị exception message, SQL hoặc stack trace cho người dùng. Log nội bộ có thể ghi chi tiết kỹ thuật với request ID, nhưng cần loại bỏ dữ liệu không nên lưu.

Một exception handler toàn cục có thể chuyển lỗi ứng dụng thành View lỗi hoặc response API. Cần phân biệt request HTML với request JSON để không trả trang HTML cho API client.

## 22. Bảo mật các thao tác quản lý sách

Các thao tác đọc và ghi có thể có chính sách khác nhau. Với giả định danh mục đọc công khai:

- GET /books và GET /books/{id} được phép đọc.
- GET /books/new và GET /books/{id}/edit yêu cầu quyền ghi.
- POST /books và POST /books/{id} yêu cầu quyền ghi.

Các điểm cần kiểm tra:

- Quyền được xác minh ở server, không dựa vào nút bị ẩn.
- Form POST dùng CSRF token khi ứng dụng dùng cookie/session authentication.
- Không bind trực tiếp entity có trường nội bộ.
- Không nhận createdBy, updatedBy, role hoặc quyền từ form.
- Nội dung mô tả được escape khi render.
- File upload bìa sách, nếu được bổ sung sau này, cần giới hạn MIME type, kích thước và nơi lưu.
- Log không ghi toàn bộ form nếu chứa dữ liệu cá nhân hoặc thông tin nội bộ.

Nếu người dùng có thể sửa sách theo chi nhánh hoặc tenant, cần kiểm tra quyền trên từng bản ghi, không chỉ kiểm tra authority chung BOOK_CATALOG_WRITE.

## 23. Xử lý hai nhân viên sửa cùng một sách

Giả sử nhân viên A mở form chỉnh sửa. Trong lúc đó nhân viên B cập nhật cùng cuốn sách. Nếu A gửi form cũ sau B, hệ thống có thể ghi đè thay đổi của B nếu không có cơ chế phát hiện xung đột.

Một cách xử lý là optimistic locking với @Version. Khi mở form, View Model đưa version hiện tại vào form; khi gửi cập nhật, command mang expectedVersion. Application service so sánh version người dùng đã đọc với version hiện tại:

~~~java
@Version
private long version;
~~~

Form hoặc command mang version đã đọc. Khi lưu, ORM kiểm tra version hiện tại. Nếu bản ghi đã thay đổi, update thất bại với optimistic locking exception.

So sánh expectedVersion trong use case phát hiện trường hợp một nhân viên mở form cũ rồi gửi sau khi người khác đã cập nhật. @Version của ORM tiếp tục bảo vệ khoảng thời gian giữa lúc service đọc entity và lúc transaction ghi commit, tránh một cập nhật đồng thời chen vào sau bước so sánh.

Ứng dụng có thể:

- Trả trang thông báo rằng dữ liệu đã được người khác cập nhật.
- Yêu cầu tải lại dữ liệu mới trước khi sửa tiếp.
- Hiển thị khác biệt để nhân viên quyết định cách hợp nhất nếu nghiệp vụ cần.

Không nên âm thầm ghi đè thay đổi mới hơn. Với danh mục đơn giản và ít người sửa, optimistic locking thường nhẹ hơn việc khóa pessimistic trong suốt thời gian người dùng mở form.

## 24. Kiểm thử bốn use case

Nên kiểm thử từng trách nhiệm và một số luồng tích hợp.

### 24.1. Unit test cho domain

- Tạo sách với tiêu đề hợp lệ thành công.
- Từ chối tiêu đề rỗng.
- Cập nhật thông tin không làm thay đổi ID.
- Chuẩn hóa ISBN theo quy tắc.
- Kiểm tra checksum ISBN-10/ISBN-13.

### 24.2. Repository test

- Tìm kiếm theo tiêu đề, tác giả và ISBN.
- Lọc theo thể loại.
- Phân trang và sắp xếp ổn định.
- Ràng buộc unique ISBN được database thực thi.
- Truy vấn chi tiết trả đúng sách.

### 24.3. Application service test

- Tạo sách khi ISBN chưa tồn tại.
- Từ chối ISBN trùng.
- Cập nhật sách tồn tại.
- Báo không tìm thấy khi ID không tồn tại.
- Không lưu khi validation nghiệp vụ thất bại.
- Xử lý xung đột cập nhật theo chính sách.

### 24.4. MVC test với MockMvc

~~~java
@WebMvcTest(BookController.class)
class BookControllerTest {
    @Autowired
    MockMvc mockMvc;

    @MockBean
    BookQueryService queryService;

    @Test
    void detailRendersBookView() throws Exception {
        UUID id = UUID.randomUUID();
        given(queryService.getDetail(id))
                .willReturn(new BookDetailView(
                        id,
                        "Clean Code",
                        "Robert C. Martin",
                        "9780132350884",
                        "Prentice Hall",
                        LocalDate.of(2008, 8, 1),
                        "Software",
                        "A book about clean code.",
                        Instant.parse("2026-01-01T00:00:00Z"),
                        0L
                ));

        mockMvc.perform(get("/books/{id}", id))
                .andExpect(status().isOk())
                .andExpect(view().name("books/detail"))
                .andExpect(model().attributeExists("book"));
    }
}
~~~

Test này xác minh route, View name và model attribute. Nó không kiểm tra query database hoặc render template thật; các hành vi đó cần test ở phạm vi tương ứng.

### 24.5. Kiểm thử validation và quyền

Các tình huống cần có:

- POST tạo sách với tiêu đề rỗng trả lại form và lỗi.
- POST tạo sách hợp lệ gọi use case đúng command.
- Người không có quyền không thể tạo hoặc sửa dù gửi request trực tiếp.
- GET ID không tồn tại trả 404.
- ISBN trùng được ánh xạ thành lỗi phù hợp.
- Request POST thiếu CSRF token bị từ chối khi CSRF được bật.
- Hai cập nhật cùng version tạo xung đột thay vì ghi đè âm thầm.

## 25. Ma trận yêu cầu và nơi triển khai

| Yêu cầu | Controller | Application/Domain | Repository | View |
|---|---|---|---|---|
| Hiển thị danh sách | Nhận query và phân trang | Chuẩn hóa tiêu chí tìm | Tìm kiếm và phân trang | Bảng, bộ lọc, phân trang |
| Xem chi tiết | Nhận ID, chọn View | Lấy và ánh xạ chi tiết | Tìm theo ID | Hiển thị thông tin |
| Tạo sách | Bind, validate, gọi use case, redirect | Kiểm tra quy tắc và tạo sách | Kiểm tra/lưu ISBN duy nhất | Form và lỗi |
| Sửa sách | Nhận ID, bind form, redirect | Kiểm tra quyền/trạng thái, cập nhật | Đọc và lưu bản ghi | Form điền sẵn |

Bảng này là điểm kiểm tra quan trọng khi review. Nếu Controller đang tự tính quy tắc nghiệp vụ, View đang truy vấn repository hoặc Repository đang quyết định thông báo cho người dùng, trách nhiệm đã bị đặt sai chỗ.

## 26. Lộ trình triển khai

Có thể triển khai theo thứ tự sau:

1. Xác nhận actor, quyền và phạm vi dữ liệu sách.
2. Định nghĩa schema và quy tắc ISBN, tiêu đề, tác giả.
3. Tạo domain model và repository contract.
4. Tạo query service cho danh sách và chi tiết.
5. Tạo command service cho tạo mới và cập nhật.
6. Tạo form DTO, validation và mapper.
7. Tạo Controller cho bốn use case.
8. Tạo View danh sách, chi tiết và form dùng chung.
9. Cấu hình security, CSRF và exception mapping.
10. Viết unit, repository, application và MVC tests.
11. Kiểm tra phân trang, tìm kiếm, xung đột cập nhật và khả năng truy cập giao diện.

Nên hoàn thành một luồng dọc nhỏ, chẳng hạn danh sách và chi tiết, trước khi mở rộng tạo/sửa. Cách này giúp xác minh routing, persistence và template engine sớm.

## 27. Những lỗi thiết kế thường gặp

### Đưa toàn bộ nghiệp vụ vào Controller

Controller trở nên dài, khó tái sử dụng và khó kiểm thử độc lập. Chuyển điều phối use case sang application service và quy tắc vào domain model.

### Dùng entity làm form binding object

Client có thể gửi thêm trường nội bộ mà form không dự định cho phép sửa. Dùng BookForm riêng và chỉ ánh xạ các trường được chấp nhận.

### Dùng một DTO cho form, database và response

Ba ranh giới có mục đích khác nhau. Tách form DTO, command/result và View DTO để tránh lộ trường hoặc coupling persistence.

### Tải toàn bộ danh sách rồi phân trang trong bộ nhớ

Chi phí tăng theo kích thước danh mục. Dùng phân trang và lọc tại database.

### Chỉ kiểm tra ISBN trùng bằng query trước khi insert

Hai request đồng thời vẫn có thể cùng vượt qua query. Database unique constraint là lớp bảo vệ cuối cùng.

### Cho View tự tải dữ liệu

Template có thể gây truy vấn ngoài dự kiến và phụ thuộc persistence. Chuẩn bị View Model trong query service.

### Ẩn nút sửa và xem đó là bảo mật

Người dùng có thể gọi URL trực tiếp. Server phải kiểm tra authority và quyền trên bản ghi.

### Không xử lý cập nhật đồng thời

Nhân viên có thể ghi đè thay đổi của nhau. Dùng version hoặc chính sách xung đột phù hợp.

### Form lỗi bị mất dữ liệu phụ trợ

Khi render lại form, Controller cần cung cấp lại model attributes cần thiết như danh sách thể loại, ID và dữ liệu hiển thị.

## 28. Checklist nghiệm thu ứng dụng quản lý sách

- [ ] Danh sách hiển thị sách theo thứ tự mặc định.
- [ ] Có tìm kiếm, lọc và phân trang.
- [ ] Trạng thái rỗng được trình bày rõ.
- [ ] Mỗi dòng có liên kết đến chi tiết đúng sách.
- [ ] Trang chi tiết hiển thị các trường đã thống nhất.
- [ ] ID không tồn tại trả 404.
- [ ] Form tạo mới có validation và thông báo lỗi theo trường.
- [ ] Tạo thành công lưu đúng một bản ghi và redirect theo PRG.
- [ ] ISBN được chuẩn hóa và có ràng buộc unique.
- [ ] Form sửa được điền dữ liệu hiện tại.
- [ ] Cập nhật không tạo bản ghi mới và không âm thầm ghi đè phiên bản mới.
- [ ] Chỉ actor có quyền được tạo/sửa ở phía server.
- [ ] CSRF được bật cho form dùng session/cookie.
- [ ] View hiển thị dữ liệu động bằng cơ chế escape an toàn.
- [ ] Controller không chứa quy tắc nghiệp vụ hoặc truy vấn persistence trực tiếp.
- [ ] View không truy cập repository.
- [ ] Có unit, repository, application và MVC test phù hợp.

## Kết luận

Bốn yêu cầu danh sách, xem chi tiết, tạo mới và sửa thông tin sách tạo thành một ví dụ MVC hoàn chỉnh ở mức cơ bản. Controller tiếp nhận request, binding và validation; application service thực hiện use case; domain model bảo vệ quy tắc; repository lưu và truy vấn dữ liệu; View trình bày DTO đã được chuẩn bị. Khi xác định rõ actor, dữ liệu, route, điều kiện chấp nhận, lỗi và quyền truy cập trước khi viết code, nhóm có thể triển khai từng luồng một cách nhất quán. Việc tách form DTO, command/result và View DTO, kết hợp phân trang, unique constraint, CSRF, optimistic locking và kiểm thử theo từng tầng giúp ví dụ nhỏ này phản ánh những quyết định quan trọng của một ứng dụng MVC thực tế.
