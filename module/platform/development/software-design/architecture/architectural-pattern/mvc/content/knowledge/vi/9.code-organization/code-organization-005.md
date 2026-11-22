# Quy ước tên cho hành động, dữ liệu nhập và dữ liệu trình bày

Trong module **MODEL_VIEW_CONTROLLER**, tên gọi của lớp, phương thức và trường dữ liệu giúp người đọc nhận ra trách nhiệm của từng thành phần. Một Controller có thể nhận request, một dịch vụ ứng dụng có thể thực hiện ca sử dụng, Model có thể bảo vệ quy tắc nghiệp vụ và View có thể trình bày kết quả. Nếu tất cả đều dùng những tên chung như handle, data, model hoặc result, người đọc phải mở nhiều lớp mới hiểu được luồng xử lý.

Bài học thuộc chương **Tổ chức mã**. Trọng tâm là quy ước đặt tên cho ba nhóm thường đi qua ranh giới MVC: **hành động**, **dữ liệu đầu vào** và **dữ liệu trình bày**. Ta sẽ xây dựng cách đặt tên nhất quán từ URL và Controller action đến command/query, request DTO, domain object, view model và response DTO; sau đó áp dụng vào một ví dụ Java Spring MVC.

## 1. Vì sao quy ước tên quan trọng?

Tên gọi là một phần của hợp đồng trong mã nguồn. Khi một phương thức có tên createBook, người đọc kỳ vọng nó tạo sách; khi một kiểu có tên CreateBookRequest, người đọc hiểu đó là dữ liệu nhận từ bên ngoài để yêu cầu tạo sách; khi một kiểu có tên BookDetailViewModel, người đọc hiểu nó được chuẩn bị cho một màn hình chi tiết.

Tên rõ ràng giúp:

- Nhìn ra ý định của hành động mà không cần đọc toàn bộ phần triển khai.
- Phân biệt dữ liệu do client gửi với dữ liệu miền mà hệ thống tin cậy.
- Nhận biết dữ liệu dành cho giao diện và dữ liệu công khai của API.
- Tìm nhanh điểm bắt đầu của một ca sử dụng trong IDE.
- Giảm việc truyền nhầm kiểu dữ liệu qua các tầng.
- Hỗ trợ review, refactor và kiểm thử vì vai trò của từng thành phần dễ nhận ra.

Ví dụ, hai phương thức sau có thể cùng gọi một dịch vụ nhưng biểu đạt mức ý nghĩa khác nhau:

~~~java
public Object handle(Object data) {
    return service.execute(data);
}
~~~

~~~java
public BookDetailViewModel showBook(BookId bookId) {
    var book = books.getDetails(bookId);
    return bookViewMapper.toDetailViewModel(book);
}
~~~

Tên ở ví dụ thứ hai cho biết hành động, dữ liệu đầu vào và kết quả trình bày. Người đọc vẫn cần xem phần triển khai để hiểu quy tắc chi tiết, nhưng không phải suy đoán mục đích của phương thức.

## 2. Nguyên tắc đặt tên chung

Một quy ước hữu ích cần nhất quán trong toàn bộ module, nhưng không nên biến thành quy tắc máy móc. Hãy bắt đầu bằng các nguyên tắc sau:

1. **Dùng từ ngữ của nghiệp vụ.** Nếu người dùng và chuyên gia nghiệp vụ gọi thao tác là phát hành sách, dùng publishBook hoặc issueBook theo đúng nghĩa đã thống nhất; không đặt tên kỹ thuật mơ hồ như changeStatus.
2. **Tên phản ánh vai trò.** Thêm hậu tố Request, Command, Query, Form, ViewModel hoặc Response khi nó giúp nhận ra ranh giới dữ liệu.
3. **Một tên, một ý nghĩa.** Không dùng cùng một kiểu BookModel lúc là entity miền, lúc là dữ liệu form và lúc là view model.
4. **Đặt tên cụ thể vừa đủ.** BookDetailViewModel có ích hơn Data; nhưng không cần đặt tên dài như BookDetailViewModelForBookDetailPage.
5. **Giữ cách viết nhất quán.** Cùng một khái niệm nên dùng cùng một từ trong route, action, use case, thông báo và tài liệu.
6. **Ưu tiên từ đầy đủ, phổ biến.** Chỉ dùng viết tắt quen thuộc và có nghĩa ổn định như id, URL, DTO hoặc API; tránh tự tạo viết tắt khó đoán.
7. **Không mã hóa chi tiết triển khai vào tên nghiệp vụ.** Tên use case nên mô tả việc cần làm, không nên phụ thuộc vào JPA, SQL hay tên framework.

Tên tốt phải giúp người đọc dự đoán được trách nhiệm. Nếu tên cần một đoạn chú thích dài mới giải thích được, hãy xem lại ranh giới hoặc cách diễn đạt.

## 3. Quy ước tên cho hành động

Tên hành động nên bắt đầu bằng động từ và chỉ rõ đối tượng hoặc kết quả mà hành động tác động đến. Với Java, phương thức thường dùng lowerCamelCase; tên lớp và record dùng UpperCamelCase.

### 3.1. Chọn động từ theo ý định

| Ý định | Động từ thường dùng | Ví dụ |
|---|---|---|
| Đọc một tài nguyên | get, find, load | getBook, findBookByIsbn |
| Đọc danh sách hoặc tìm kiếm | list, search | listBooks, searchBooks |
| Tạo một tài nguyên | create, register | createBook, registerMember |
| Thay đổi thông tin | update, rename, change | updateBook, renameBook |
| Xóa hoặc ngừng sử dụng | delete, remove, archive | deleteBook, archiveBook |
| Chuyển trạng thái nghiệp vụ | publish, approve, cancel, issue, return | publishBook, approveLoan |
| Kiểm tra điều kiện | exists, is, has, can | existsByIsbn, canDeleteBook |
| Tính toán | calculate, estimate, derive | calculateLateFee |

Động từ cần phản ánh ngôn ngữ miền. Ví dụ, nếu thao tác “đóng khoản vay” có quy tắc nghiệp vụ khác với “xóa khoản vay”, không dùng deleteLoan cho cả hai. Một tên kỹ thuật chung như updateStatus cũng không diễn tả được ý định approveLoan hoặc cancelLoan.

### 3.2. Phân biệt get, find và search

Có thể chọn một quy ước nội bộ như:

- **get** khi caller yêu cầu một tài nguyên theo định danh và thiếu tài nguyên là lỗi của ca sử dụng.
- **find** khi kết quả có thể không tồn tại và phương thức trả Optional hoặc một kiểu kết quả tương đương.
- **search** khi caller cung cấp tiêu chí truy vấn, bộ lọc hoặc từ khóa.
- **list** khi mục tiêu là lấy một tập hợp theo phạm vi hoặc thứ tự đã xác định.

Ví dụ:

~~~java
Book getBook(BookId bookId);

Optional<Book> findBookByIsbn(Isbn isbn);

Page<BookSummary> searchBooks(SearchBooksQuery query);

List<BookSummary> listRecentlyPublishedBooks();
~~~

Đây là quy ước có thể lựa chọn cho dự án; điều quan trọng là toàn nhóm dùng nhất quán và kiểu trả về phù hợp với tên. Không nên có phương thức tên getBook nhưng trả null tùy ý, hoặc tên findBook nhưng ném lỗi “không tìm thấy” trong mọi trường hợp mà không có lý do.

### 3.3. Tên action trong Controller

Controller action là điểm tiếp nhận giao thức, nên tên phương thức cần giúp người đọc hiểu endpoint đang phục vụ thao tác nào:

~~~java
@GetMapping("/{bookId}")
public BookDetailViewModel showBook(@PathVariable UUID bookId) {
    return bookQueries.getDetail(new BookId(bookId));
}

@PostMapping
public ResponseEntity<BookResponse> createBook(
    @Valid @RequestBody CreateBookRequest request
) {
    // Điều phối ca sử dụng tạo sách
}

@PostMapping("/{bookId}/publish")
public ResponseEntity<Void> publishBook(@PathVariable UUID bookId) {
    // Điều phối ca sử dụng phát hành sách
}
~~~

Tên phương thức Java không nhất thiết tạo ra URL. Trong Spring MVC, annotation quyết định route và HTTP method; tên action giúp tổ chức mã nguồn. Vì vậy, không cần đặt tên phương thức theo toàn bộ URL, ví dụ getApiBooksByBookId. Hãy dùng tên diễn đạt nghiệp vụ và để annotation thể hiện hợp đồng HTTP.

### 3.4. Một action nên có một ý định chính

Tránh action kiểu process, handleRequest hoặc executeAction nếu nó có thể tạo, sửa, xóa hoặc phát hành tùy một cờ mode. Một action xử lý nhiều ý định không liên quan thường làm khó phân quyền, validation và kiểm thử.

Thay vào đó, tách theo ý định:

- createBook cho việc tạo sách.
- updateBook cho việc cập nhật thông tin.
- publishBook cho việc phát hành.
- archiveBook cho việc lưu trữ.

Nếu nhiều action chia sẻ bước kỹ thuật, hãy trích phần dùng chung vào một thành phần phù hợp. Không cần gom nhiều nghiệp vụ thành một phương thức chỉ để giảm số dòng code.

## 4. Tên route và tên phương thức có liên quan nhưng không giống nhau

Route là hợp đồng giao tiếp với client; tên phương thức là cách tổ chức mã nguồn. Với REST-style API, route thường dùng danh từ biểu diễn tài nguyên, còn HTTP method thể hiện loại thao tác.

| Hành động | Route minh họa | Controller action |
|---|---|---|
| Đọc danh sách | GET /api/books | listBooks |
| Đọc chi tiết | GET /api/books/{bookId} | showBook |
| Tạo sách | POST /api/books | createBook |
| Cập nhật sách | PUT /api/books/{bookId} | updateBook |
| Xóa sách | DELETE /api/books/{bookId} | deleteBook |
| Phát hành sách | POST /api/books/{bookId}/publish | publishBook |

Không cần đưa động từ CRUD vào mọi URL như /getBooks hoặc /createBook nếu API đang theo quy ước tài nguyên. Một hành động nghiệp vụ có ý nghĩa riêng như publish hoặc approve có thể có endpoint hành động rõ ràng.

Các quy tắc nên giữ nhất quán:

- Dùng danh từ số nhiều cho collection nếu đó là quy ước API của dự án.
- Dùng path variable có tên theo đối tượng, chẳng hạn bookId.
- Dùng query parameter cho tiêu chí tìm kiếm, lọc, sắp xếp và phân trang.
- Không dùng GET cho hành động làm thay đổi trạng thái.
- Không đặt tên route theo tên lớp Java nội bộ nếu tên đó không thuộc ngôn ngữ API.

Nếu dự án dùng quy ước khác, hãy tuân theo quy ước đã được công bố thay vì pha trộn hai phong cách.

## 5. Quy ước tên cho dữ liệu đầu vào

Dữ liệu đầu vào đi từ một ranh giới bên ngoài vào ứng dụng. Trong MVC web, nó có thể đến từ path, query string, header, JSON body hoặc HTML form. Tên kiểu dữ liệu cần chỉ ra nguồn gốc hoặc mục đích của nó.

### 5.1. Request DTO

Request DTO mô tả dữ liệu client được phép gửi cho một endpoint. Nên đặt tên theo hành động hoặc truy vấn:

- CreateBookRequest
- UpdateBookRequest
- SearchBooksRequest
- ChangeBookStatusRequest

Không nên dùng BookRequest chung nếu ứng dụng có nhiều thao tác với tập trường khác nhau. Tên theo hành động giúp người đọc biết DTO thuộc endpoint nào và tránh vô tình dùng lại dữ liệu đầu vào có quyền chỉnh sửa khác nhau.

~~~java
public record CreateBookRequest(
    String title,
    String author,
    String isbn
) {}

public record UpdateBookRequest(
    String title,
    String author
) {}
~~~

CreateBookRequest có thể nhận ISBN lúc tạo; UpdateBookRequest không nhất thiết cho phép sửa ISBN nếu nghiệp vụ không hỗ trợ. Tách hai kiểu làm rõ hợp đồng và giảm nguy cơ mass assignment.

### 5.2. Form model

Với server-rendered MVC, dữ liệu biểu mẫu có thể được đặt tên theo mục đích hiển thị và binding:

- CreateBookForm
- EditBookForm
- SearchBooksForm

Form model có thể chứa giá trị nhập, lỗi validation và lựa chọn hiển thị. Nó thuộc biên giao diện và có thể khác request DTO của API. Nếu form có trường như confirmPassword hoặc một chuỗi ngày theo định dạng địa phương, không nên ép nó trở thành domain object.

### 5.3. Command và Query

Command biểu diễn ý định thay đổi trạng thái; Query biểu diễn yêu cầu đọc dữ liệu. Đây là tên thường dùng ở tầng ứng dụng, không phải bắt buộc cho mọi MVC project.

~~~java
public record CreateBookCommand(
    String title,
    String author,
    Isbn isbn
) {}

public record SearchBooksQuery(
    String keyword,
    String category,
    int page,
    int pageSize
) {}
~~~

Tên command nên bắt đầu bằng động từ nghiệp vụ, chẳng hạn CreateBookCommand, PublishBookCommand hoặc CancelLoanCommand. Tên query có thể dùng GetBookDetailsQuery, SearchBooksQuery hoặc ListActiveLoansQuery.

Không đặt tên mọi đầu vào là Request nếu nó không còn thuộc giao thức HTTP. Khi DTO HTTP được chuyển thành command, tên mới giúp tách hợp đồng bên ngoài khỏi ý định mà ứng dụng thực hiện.

### 5.4. Tên trường đầu vào

Tên field nên diễn đạt dữ liệu, không phải widget giao diện:

| Nên dùng | Tránh dùng | Lý do |
|---|---|---|
| title | txtTitle | Không gắn với loại control |
| pageSize | page | Phân biệt số dòng mỗi trang với số trang |
| publishedFrom | date1 | Nêu rõ ý nghĩa bộ lọc |
| includeArchived | checkbox2 | Diễn đạt lựa chọn |
| isbn | isbnTextBox | Không phụ thuộc giao diện |
| confirmPassword | inputPasswordAgain | Thể hiện vai trò xác nhận |

Không thêm tiền tố txt, btn, ddl hoặc chk vào tên thuộc tính dữ liệu. Những tiền tố này mô tả thành phần UI và làm kiểu dữ liệu bị gắn vào cách bố trí hiện tại.

Tên field phải phù hợp với kiểu và đơn vị. Nếu giá trị là số tiền, cân nhắc dùng Money hoặc đặt rõ currency; nếu là thời lượng, ưu tiên Duration hoặc nêu đơn vị như timeoutMs. Tránh field amount hoặc duration khi người đọc không thể biết đơn vị hay ý nghĩa.

## 6. Quy ước tên cho Model miền

Model miền mô tả khái niệm nghiệp vụ, nên tên thường là danh từ hoặc cụm danh từ trong ngôn ngữ miền.

Ví dụ:

- Book, Member, Loan, Invoice là các khái niệm có định danh hoặc vòng đời.
- Isbn, Money, Address, DateRange là các giá trị có ý nghĩa.
- BookStatus, LoanState, PaymentMethod là các kiểu mô tả trạng thái hoặc phân loại.
- PricingPolicy, LoanEligibilityPolicy là các chính sách nghiệp vụ nếu miền thực sự có khái niệm đó.

Không đặt tên domain object theo màn hình như BookListRow hoặc BookEditModel. Đó là tên phù hợp hơn cho kiểu trình bày hoặc dữ liệu đầu vào.

### 6.1. Tên Entity và Value Object

Entity thường có tên danh từ số ít: Book, Member, Loan. Value Object cũng dùng danh từ biểu diễn giá trị: Isbn, Money, EmailAddress.

Hành vi của Model nên dùng động từ nghiệp vụ:

~~~java
public final class Book {
    public void rename(String newTitle) {
        // Bảo vệ quy tắc đổi tên
    }

    public void publish() {
        // Kiểm tra điều kiện và chuyển trạng thái
    }

    public void archive() {
        // Áp dụng chính sách lưu trữ
    }
}
~~~

Không dùng setStatus(String status) làm API chính cho một chuyển đổi nghiệp vụ có điều kiện. Một phương thức publish() diễn đạt rõ ý định và có thể bảo vệ bất biến bên trong đối tượng.

### 6.2. Tránh tên phụ thuộc persistence

Nếu Book là đối tượng miền, không nên đổi thành BookJpaEntity chỉ vì nó được lưu bằng JPA. Hậu tố Jpa hoặc Entity phù hợp với lớp adapter/persistence khi có một kiểu riêng dành cho ORM, ví dụ BookEntity hoặc BookJpaEntity.

Khi một kiểu vừa là domain object vừa là ORM entity trong ứng dụng nhỏ, tên Book vẫn có thể phù hợp. Đừng tạo hậu tố chỉ để mô tả công nghệ nếu nó không giúp phân biệt vai trò.

### 6.3. Đặt tên cho identifier và collection

Dùng BookId thay vì id kiểu String ở những nơi cần bảo vệ kiểu định danh. Trong tham số, dùng bookId thay vì id nếu phương thức có nhiều loại ID.

Tên collection nên ở dạng số nhiều: books, activeLoans, publishedBooks. Tên một phần tử dùng số ít: book, loan. Tránh tên chung như items nếu kiểu hoặc ngữ cảnh không cho biết phần tử là gì.

## 7. Quy ước tên cho dữ liệu trình bày

Dữ liệu trình bày được chuẩn bị để View hiển thị. Nó có thể chứa thông tin tổng hợp, nhãn, trạng thái có thể hiển thị, quyền hiển thị nút hoặc dữ liệu đã định dạng. Tên cần phân biệt nó với Model miền và request.

### 7.1. ViewModel

Một ViewModel thường được đặt tên theo màn hình hoặc mục đích trình bày:

- BookListViewModel
- BookDetailViewModel
- EditBookPageViewModel
- DashboardViewModel

Với Spring MVC, ViewModel có thể được đưa vào Model của framework hoặc được trả trực tiếp từ controller theo cách tổ chức của ứng dụng. Tên ViewModel giúp tránh nhầm nó với đối tượng miền Book.

Ví dụ:

~~~java
public record BookDetailViewModel(
    UUID id,
    String title,
    String authorName,
    String formattedIsbn,
    String publicationLabel,
    boolean canEdit,
    boolean canArchive
) {}
~~~

ViewModel có thể chứa canEdit hoặc publicationLabel vì đó là thông tin cần để trình bày. Tuy nhiên, server vẫn phải kiểm tra quyền khi nhận request sửa hoặc lưu trữ; giá trị canEdit chỉ hỗ trợ giao diện quyết định có hiển thị nút hay không.

### 7.2. Response DTO cho API

Response DTO là hợp đồng dữ liệu trả về cho client API. Có thể đặt tên như:

- BookResponse
- BookSummaryResponse
- BookDetailResponse
- JobStatusResponse

Không trả trực tiếp domain object hoặc ORM entity nếu điều đó làm lộ trường nội bộ, quan hệ lazy hoặc cấu trúc lưu trữ. Response DTO chỉ nên chứa trường được phép công khai.

Một response cho màn hình danh sách có thể khác response chi tiết:

~~~java
public record BookSummaryResponse(
    UUID id,
    String title,
    String authorName
) {}

public record BookDetailResponse(
    UUID id,
    String title,
    String authorName,
    String isbn,
    String status,
    Instant publishedAt
) {}
~~~

Tách kiểu khi hợp đồng đọc có phạm vi hoặc vòng đời khác nhau. Nếu hai endpoint thật sự có cùng hợp đồng và cùng ý nghĩa, có thể dùng chung một response type thay vì nhân bản vô ích.

### 7.3. View data và tên thuộc tính

Tên thuộc tính ViewModel nên diễn đạt nội dung mà template cần:

| Tên thuộc tính | Ý nghĩa |
|---|---|
| pageTitle | Tiêu đề trang |
| books | Danh sách sách để hiển thị |
| emptyMessage | Thông báo khi không có dữ liệu |
| selectedCategory | Danh mục đang chọn |
| currentPage | Trang hiện tại |
| totalPages | Tổng số trang |
| canEdit | Có thể hiển thị thao tác sửa |
| createdAtLabel | Ngày tạo đã định dạng để trình bày |

Tránh tên như data1, object, model hoặc value nếu có thể dùng tên cụ thể. Một template chứa nhiều thuộc tính chung chung khiến người đọc phải lần ngược Controller hoặc mapper mới hiểu dữ liệu.

## 8. Quy ước cho mapper và chuyển đổi dữ liệu

Tên mapper nên nói rõ hai phía của chuyển đổi. Các phương thức có thể dùng:

- toCommand(CreateBookRequest request)
- toDomain(BookEntity entity)
- toEntity(Book book)
- toDetailViewModel(Book book)
- toResponse(Book book)

Ví dụ:

~~~java
public final class BookViewMapper {
    public BookDetailViewModel toDetailViewModel(Book book) {
        return new BookDetailViewModel(
            book.id().value(),
            book.title(),
            book.author().displayName(),
            book.isbn().value(),
            book.status().displayName(),
            false,
            false
        );
    }
}
~~~

Trong ứng dụng thực tế, quyền hiển thị có thể cần ngữ cảnh người dùng; khi đó mapper nhận một view context hoặc application service chuẩn bị trường canEdit/canArchive. Không để mapper âm thầm truy cập database hoặc thực hiện quy tắc nghiệp vụ.

Nếu có nhiều nguồn dữ liệu, tên phương thức nên thể hiện rõ chiều chuyển đổi. Tránh map(), convert() hoặc transform() không có ngữ cảnh khi lớp có nhiều trách nhiệm.

## 9. Quy tắc cho boolean, phương thức kiểm tra và giá trị đặc biệt

Tên boolean nên đọc được như một câu hỏi hoặc trạng thái:

- isPublished
- hasActiveLoan
- canDelete
- requiresApproval
- supportsArchive

Với Java record, tên component có thể là published, active hoặc archived; method truy cập sẽ là published(). Nếu dự án muốn giữ tiền tố is cho field boolean, hãy dùng nhất quán và lưu ý quy ước của framework binding/serialization.

Tên predicate nên trả về boolean và diễn đạt điều kiện:

~~~java
boolean isPublished();
boolean hasActiveLoan(BookId bookId);
boolean canArchive(Book book, UserId actorId);
boolean existsByIsbn(Isbn isbn);
~~~

Tránh tên phủ định kép như isNotUnavailable. Dùng available hoặc isAvailable để biểu đạt trạng thái tích cực. Nếu điều kiện phức tạp, có thể đặt tên theo quy tắc nghiệp vụ như isEligibleForPublication.

Với giá trị số, thêm đơn vị nếu tên không tự nói rõ:

- timeoutMs cho số mili giây.
- retryCount cho số lần thử.
- pageSize cho số phần tử mỗi trang.
- amountVnd nếu biểu diễn số tiền theo VND và chưa dùng Money type.

Nếu có thể, dùng kiểu miền như Duration, Money hoặc PageRequest để tránh nhầm đơn vị và phạm vi.

## 10. Tính nhất quán giữa các tầng

Cùng một ý định nghiệp vụ nên có chuỗi tên liên quan và dễ lần theo. Ví dụ thao tác tạo sách:

| Ranh giới | Tên gợi ý | Vai trò |
|---|---|---|
| API route | POST /api/books | Hợp đồng HTTP |
| Controller | createBook | Tiếp nhận và điều phối |
| Request DTO | CreateBookRequest | Dữ liệu client gửi |
| Command | CreateBookCommand | Ý định ứng dụng |
| Application Service | createBook | Thực hiện ca sử dụng |
| Domain Model | Book.register | Tạo đối tượng hợp lệ |
| Repository | save | Lưu đối tượng |
| Response DTO | BookResponse | Dữ liệu API trả về |
| ViewModel | BookDetailViewModel | Dữ liệu cho trang chi tiết |

Không nhất thiết mọi tầng phải có một lớp riêng. Bảng chỉ cho thấy cách đặt tên khi các ranh giới đó tồn tại. Nếu ứng dụng nhỏ chưa cần command riêng, Controller có thể chuyển Request DTO sang một dịch vụ ứng dụng với kiểu phù hợp. Đừng tạo lớp chỉ để tên gọi trông đầy đủ.

### 10.1. Không để một tên bị dùng cho nhiều vai trò

Ví dụ, kiểu BookModel có thể bị hiểu là:

- Domain Model.
- Spring MVC model attribute.
- ViewModel của trang.
- Entity được ORM ánh xạ.
- Request body của API.

Khi có nhiều nghĩa, hãy dùng tên cụ thể như Book, BookEntity, CreateBookRequest hoặc BookDetailViewModel. Việc thêm hậu tố không phải mục tiêu tự thân; mục tiêu là loại bỏ sự mơ hồ tại ranh giới.

### 10.2. Tên nghiệp vụ nhất quán hơn tên kỹ thuật

Giả sử giao diện có nút “Phát hành”. Hãy dùng cùng một thuật ngữ trong tài liệu, action và ca sử dụng nếu chúng mô tả cùng ý định:

- publishBook
- PublishBookCommand
- publishBook trong application service
- Book.publish()

Không đổi qua lại giữa activate, enable, approve và publish nếu các từ đó không có nghĩa giống nhau trong miền. Ngược lại, nếu approve là bước phê duyệt và publish là bước công khai, hãy giữ hai tên riêng để thể hiện hai hành động khác nhau.

## 11. Package và tên file trong dự án Java

Package nên viết chữ thường, theo nhóm trách nhiệm hoặc feature. Tên lớp và file Java dùng UpperCamelCase và khớp tên kiểu công khai.

Một cấu trúc theo feature có thể là:

~~~text
book/
  web/
    BookController.java
    CreateBookRequest.java
    UpdateBookRequest.java
    BookResponse.java
    BookDetailViewModel.java
    BookRequestMapper.java
  application/
    CreateBookCommand.java
    SearchBooksQuery.java
    BookApplicationService.java
  domain/
    Book.java
    BookId.java
    Isbn.java
    BookRepository.java
  infrastructure/
    BookJpaEntity.java
    JpaBookRepository.java
    BookPersistenceMapper.java
~~~

Cấu trúc thực tế có thể tổ chức theo layer hoặc feature tùy quy mô. Dù chọn cách nào, tên package nên cho biết vai trò và không nên tạo một package model chứa tất cả request, entity, response và view model không liên quan.

Nếu dùng tên package controller, service, repository, hãy bảo đảm nhóm lớp trong đó có phạm vi nhất quán. Với ứng dụng lớn, tổ chức theo feature có thể giúp một nhóm thay đổi liên quan nằm gần nhau; trong mỗi feature vẫn có thể chia web, application, domain và infrastructure.

## 12. Ví dụ hoàn chỉnh: từ form đến ViewModel

Giả sử người dùng tạo một cuốn sách trong ứng dụng quản lý thư viện. Các kiểu được đặt tên theo vai trò:

~~~java
public record CreateBookForm(
    String title,
    String authorName,
    String isbn
) {}

public record CreateBookCommand(
    String title,
    String authorName,
    Isbn isbn
) {}

public record BookDetailViewModel(
    UUID id,
    String title,
    String authorName,
    String isbn,
    String statusLabel
) {}
~~~

Controller xử lý giao thức và chọn View:

~~~java
@Controller
@RequestMapping("/books")
public class BookPageController {
    private final BookApplicationService books;
    private final BookViewMapper viewMapper;

    public BookPageController(
        BookApplicationService books,
        BookViewMapper viewMapper
    ) {
        this.books = books;
        this.viewMapper = viewMapper;
    }

    @GetMapping("/new")
    public String showCreateBookForm(Model model) {
        model.addAttribute("form", new CreateBookForm("", "", ""));
        return "books/new";
    }

    @PostMapping
    public String createBook(
        @Valid @ModelAttribute("form") CreateBookForm form,
        BindingResult errors,
        RedirectAttributes redirect
    ) {
        if (errors.hasErrors()) {
            return "books/new";
        }

        var command = new CreateBookCommand(
            form.title(),
            form.authorName(),
            new Isbn(form.isbn())
        );

        var bookId = books.createBook(command);
        redirect.addFlashAttribute("message", "Đã tạo sách " + bookId);
        return "redirect:/books/" + bookId;
    }

    @GetMapping("/{bookId}")
    public String showBook(
        @PathVariable UUID bookId,
        Model model
    ) {
        var book = books.getBook(new BookId(bookId));
        model.addAttribute("book", viewMapper.toDetailViewModel(book));
        return "books/detail";
    }
}
~~~

Ví dụ minh họa cách đặt tên và luồng chuyển đổi. Trong ứng dụng thật, cần ánh xạ lỗi nghiệp vụ, lỗi không tìm thấy và lỗi validation nhất quán. Việc tạo Isbn có thể phát sinh lỗi miền; có thể chuyển lỗi đó thành validation error phù hợp với form.

Tên thể hiện rõ các ranh giới:

- CreateBookForm thuộc giao diện HTML và model binding.
- CreateBookCommand biểu diễn ý định của tầng ứng dụng.
- Isbn là kiểu miền bảo vệ định dạng và ý nghĩa ISBN.
- Book là đối tượng miền được dịch vụ ứng dụng tạo và lưu.
- BookDetailViewModel là dữ liệu đã chuẩn bị cho template.
- showCreateBookForm, createBook và showBook mô tả các action khác nhau.

## 13. Những anti-pattern đặt tên thường gặp

| Tên hoặc cách đặt | Vấn đề | Cách cải thiện |
|---|---|---|
| handle, process, execute | Không thể hiện ý định nghiệp vụ | Dùng createBook, publishBook hoặc searchBooks |
| data, info, object, result | Quá chung, khó biết nội dung | Dùng CreateBookRequest, BookSummary hoặc JobStatus |
| BookModel cho mọi tầng | Trộn domain, form, ORM và ViewModel | Đặt tên theo vai trò và ranh giới |
| txtTitle, btnSave | Gắn dữ liệu với control giao diện | Dùng title, saveBook |
| getBooks cho thao tác tìm kiếm có nhiều bộ lọc | Không thể hiện tiêu chí truy vấn | Dùng searchBooks |
| updateStatus | Che giấu hành động nghiệp vụ cụ thể | Dùng publishBook, archiveBook hoặc approveBook |
| isNotInvalid | Phủ định kép | Dùng isValid |
| id khi có nhiều loại định danh | Dễ truyền nhầm ID | Dùng bookId, memberId hoặc kiểu BookId |
| BookDTO cho mọi request/response | Không thể hiện chiều và mục đích | Dùng CreateBookRequest, BookResponse |
| JpaBookService trong tầng miền | Tên gắn nghiệp vụ với công nghệ lưu trữ | Để JpaBookRepository ở infrastructure |
| tên viết tắt tự tạo | Khó đọc và khó tìm kiếm | Dùng thuật ngữ đầy đủ đã thống nhất |
| một action xử lý theo mode | Trộn nhiều ý định và quyền | Tách action theo hành động nghiệp vụ |

Tên dài không tự động là tên tốt. Một tên như processBookData có thể dài hơn createBook nhưng vẫn mơ hồ. Hãy chọn tên mang đủ ngữ nghĩa để phân biệt trách nhiệm, không thêm từ chỉ để tạo cảm giác chi tiết.

## 14. Kiểm tra và duy trì quy ước tên

Quy ước tên cần được duy trì trong review và refactor, không chỉ ghi trong tài liệu. Có thể dùng checklist khi thêm endpoint hoặc kiểu dữ liệu:

- Tên action có bắt đầu bằng động từ và diễn đạt một ý định chính không?
- Tên route có tuân theo quy ước HTTP/API của dự án không?
- Request DTO có chỉ chứa trường client được phép gửi không?
- Command/Query có diễn đạt đúng ý định ứng dụng không?
- Domain object có dùng từ ngữ của nghiệp vụ không?
- ViewModel và Response DTO có chỉ rõ mục đích trình bày hoặc hợp đồng API không?
- Tên field có nêu rõ ý nghĩa, kiểu và đơn vị cần thiết không?
- Tên mapper có cho biết chiều chuyển đổi không?
- Có kiểu hoặc phương thức nào mang tên chung chung vì nhiều trách nhiệm đang bị trộn không?

Có thể bổ sung kiểm tra tự động cho quy ước package, hậu tố lớp hoặc dependency giữa các nhóm mã. Tuy nhiên, công cụ không thể quyết định một động từ có đúng nghĩa nghiệp vụ hay không; phần đó cần được thống nhất qua ngôn ngữ của nhóm và review thiết kế.

### 14.1. Refactor tên an toàn

Khi đổi tên, dùng chức năng Rename Symbol của IDE để cập nhật tham chiếu trong mã nguồn. Nếu tên route hoặc JSON field là hợp đồng công khai, đổi tên có thể phá vỡ client bên ngoài; cần versioning, alias hoặc kế hoạch tương thích trước khi thay đổi.

Với tên trường được serialize, hãy kiểm tra cấu hình Jackson hoặc annotation liên quan. Tên thuộc tính Java và tên JSON không nhất thiết phải giống nhau nếu API cần giữ hợp đồng cũ. Tương tự, đổi tên template attribute có thể ảnh hưởng các file View dùng nó.

Nên refactor theo từng ranh giới, chạy test liên quan và tìm các tham chiếu còn sót. Đừng thay hàng loạt từ khóa chung như model hoặc data mà không xác định từng trường hợp đang mang nghĩa gì.

## 15. Checklist quy ước tên cho MVC

- [ ] Controller action dùng động từ thể hiện ý định rõ ràng.
- [ ] Tên route và HTTP method tuân theo một quy ước API nhất quán.
- [ ] Request DTO/Form model có tên theo hành động hoặc truy vấn.
- [ ] Command và Query phân biệt ý định ghi với yêu cầu đọc.
- [ ] Domain Model dùng thuật ngữ nghiệp vụ, không phụ thuộc tên màn hình.
- [ ] ViewModel và Response DTO thể hiện rõ mục đích trình bày hoặc hợp đồng API.
- [ ] Boolean dùng tên có thể đọc như trạng thái hoặc câu hỏi.
- [ ] ID, collection và đơn vị được đặt tên cụ thể.
- [ ] Mapper thể hiện chiều chuyển đổi và không âm thầm chứa nghiệp vụ.
- [ ] Không dùng một kiểu chung cho nhiều ranh giới có ý nghĩa khác nhau.
- [ ] Đổi tên hợp đồng công khai có kiểm tra tương thích và kiểm thử.

Một quy ước tên tốt giúp người đọc lần theo luồng MVC từ request đến action, từ dữ liệu đầu vào đến ca sử dụng, rồi từ kết quả nghiệp vụ đến dữ liệu trình bày. Khi tên phản ánh đúng ý định và ranh giới, mã nguồn trở nên dễ tìm, dễ review và dễ thay đổi mà không cần dựa vào những quy ước ngầm trong đầu từng thành viên.
