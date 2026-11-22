# Đối tượng nghiệp vụ, đối tượng giá trị và quy tắc bất biến

## 1. Model cần biểu diễn điều gì?

Trong MVC, **Model** biểu diễn trạng thái và các khái niệm của miền nghiệp vụ mà ứng dụng đang giải quyết. Với một hệ thống quản lý thư viện, miền nghiệp vụ có thể gồm Sách, Độc giả, Phiếu mượn, ISBN, Tiền phạt và các quy tắc như một phiếu mượn không thể chứa cùng một cuốn sách hai lần.

Model không chỉ là tập hợp các lớp có trường dữ liệu để lưu xuống cơ sở dữ liệu. Một mô hình nghiệp vụ hữu ích còn thể hiện:

- Những đối tượng nào có danh tính và vòng đời riêng.
- Những giá trị nào chỉ có ý nghĩa thông qua dữ liệu cấu thành chúng.
- Những trạng thái nào được xem là hợp lệ.
- Những hành động nào được phép làm thay đổi trạng thái.
- Những điều kiện nào phải luôn đúng trong suốt vòng đời của đối tượng.

Ba khái niệm **đối tượng nghiệp vụ (Entity)**, **đối tượng giá trị (Value Object)** và **quy tắc bất biến (Invariant)** giúp mô hình hóa những điều đó. Chúng thường xuất hiện trong Domain Model và có thể được sử dụng bên trong phần Model của một ứng dụng MVC.

## 2. Đối tượng nghiệp vụ (Entity)

Entity là đối tượng được nhận diện bằng **danh tính (identity)** xuyên suốt vòng đời của nó. Các thuộc tính của Entity có thể thay đổi, nhưng đối tượng vẫn được xem là cùng một đối tượng nghiệp vụ nếu danh tính của nó không đổi.

Ví dụ, một cuốn sách trong hệ thống thư viện có mã định danh `bookId`. Tiêu đề của sách có thể được sửa, tình trạng lưu thông có thể thay đổi, nhưng đó vẫn là cuốn sách có cùng `bookId`. Hai bản ghi có tiêu đề và ISBN giống nhau chưa chắc là cùng một Entity nếu chúng có danh tính khác nhau trong miền nghiệp vụ.

### Đặc điểm của Entity

- **Có danh tính ổn định:** thường có mã định danh do miền nghiệp vụ hoặc hệ thống cấp.
- **Có vòng đời:** được tạo, thay đổi trạng thái và có thể bị ngừng sử dụng hoặc xóa theo quy tắc nghiệp vụ.
- **Có hành vi:** trạng thái nên được thay đổi thông qua các hành động có ý nghĩa, thay vì cho phép mọi nơi tùy ý ghi vào mọi thuộc tính.
- **So sánh theo danh tính:** hai Entity được xem là cùng một đối tượng khi định danh của chúng tương ứng theo quy tắc của miền, dù các thuộc tính khác nhau.

Ví dụ: sách `B-1024` được đổi tiêu đề từ “Lập trình Java” thành “Java thực hành”. Việc đổi tiêu đề không tạo ra một cuốn sách mới. Ngược lại, hai cuốn sách khác nhau có thể cùng tiêu đề nhưng vẫn là hai Entity riêng.

### Ví dụ Entity bằng Java

~~~java
import java.util.Objects;
import java.util.UUID;

public final class Book {
    private final UUID id;
    private final Isbn isbn;
    private String title;

    private Book(UUID id, Isbn isbn, String title) {
        this.id = Objects.requireNonNull(id);
        this.isbn = Objects.requireNonNull(isbn);
        this.title = requireTitle(title);
    }

    public static Book create(UUID id, Isbn isbn, String title) {
        return new Book(id, isbn, title);
    }

    public void rename(String newTitle) {
        this.title = requireTitle(newTitle);
    }

    private static String requireTitle(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Title must not be blank");
        }
        return value.trim();
    }

    public UUID id() { return id; }
    public Isbn isbn() { return isbn; }
    public String title() { return title; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof Book book)) return false;
        return id.equals(book.id);
    }

    @Override
    public int hashCode() {
        return id.hashCode();
    }
}
~~~

Trong ví dụ, `id` là danh tính của Entity. Phương thức `rename` là lối vào có chủ đích để đổi tiêu đề và kiểm tra điều kiện tiêu đề không được rỗng. `equals` và `hashCode` sử dụng định danh vì ví dụ giả định UUID đã được cấp ngay khi tạo đối tượng.

Trong ứng dụng dùng ORM, chiến lược định danh và cách viết `equals`/`hashCode` cần phù hợp với vòng đời persistence. Một số hệ thống chỉ cấp ID khi lưu lần đầu; khi đó việc dùng ID chưa được cấp trong hash collection có thể gây lỗi. Không nên sao chép nguyên xi ví dụ này mà bỏ qua quy tắc identity của framework và miền nghiệp vụ.

## 3. Đối tượng giá trị (Value Object)

Value Object là đối tượng được nhận diện bằng **giá trị của các thuộc tính**, không có danh tính riêng trong miền nghiệp vụ. Hai Value Object có cùng giá trị theo quy tắc so sánh của kiểu đó được xem là tương đương, dù chúng được tạo ở hai thời điểm hoặc hai vị trí khác nhau.

Ví dụ, ISBN `978-0-13-235088-4` và ISBN `9780132350884` có thể biểu diễn cùng một giá trị nếu quy tắc của hệ thống chuẩn hóa dấu gạch nối và khoảng trắng. Điều quan trọng là giá trị ISBN, không phải lần tạo ra đối tượng ISBN.

### Đặc điểm của Value Object

- **Không có identity riêng:** không cần mã định danh để phân biệt từng lần xuất hiện.
- **So sánh theo giá trị:** phép bằng nhau dựa trên toàn bộ thành phần có ý nghĩa của giá trị.
- **Nên bất biến (immutable):** sau khi tạo, giá trị không bị thay đổi tại chỗ. Muốn có giá trị khác thì tạo Value Object mới.
- **Tự bảo vệ tính hợp lệ:** constructor hoặc factory kiểm tra và chuẩn hóa dữ liệu trước khi cho phép tạo đối tượng.
- **Có thể kết hợp nhiều thuộc tính:** ví dụ Money gồm số tiền và đơn vị tiền tệ; chỉ so sánh số tiền mà bỏ qua currency sẽ sai.

### Ví dụ Value Object bằng Java

~~~java
import java.util.Objects;

public record Isbn(String value) {
    public Isbn {
        Objects.requireNonNull(value, "ISBN is required");
        value = value.replaceAll("[-\\s]", "").toUpperCase();

        boolean isbn10 = value.matches("[0-9]{9}[0-9X]");
        boolean isbn13 = value.matches("[0-9]{13}");
        if (!isbn10 && !isbn13) {
            throw new IllegalArgumentException("Invalid ISBN format");
        }
    }
}
~~~

Java `record` tự sinh các phương thức so sánh theo giá trị của thành phần `value`. Constructor chuẩn hóa ISBN trước khi lưu, vì vậy hai chuỗi có cách viết khác nhau nhưng cùng dạng chuẩn sẽ tạo ra các Value Object tương đương. Ví dụ này kiểm tra cấu trúc cơ bản; hệ thống nghiệp vụ cần kiểm tra thêm checksum ISBN-10/ISBN-13 nếu tính hợp lệ đầy đủ của mã là yêu cầu.

Value Object nhiều thuộc tính cũng phải đưa mọi thành phần có ý nghĩa vào phép so sánh. Chẳng hạn, `Money(100, VND)` không tương đương `Money(100, USD)`. Hai khoản tiền chỉ có cùng con số nhưng khác đơn vị tiền tệ không thể được cộng hoặc so sánh như cùng một giá trị.

## 4. Phân biệt Entity và Value Object

| Tiêu chí | Entity | Value Object |
|---|---|---|
| Cách nhận diện | Danh tính ổn định | Giá trị của các thuộc tính |
| So sánh bằng nhau | Theo identity của miền | Theo giá trị |
| Thay đổi trạng thái | Có thể thay đổi qua hành vi | Nên bất biến; thay đổi bằng cách tạo giá trị mới |
| Vòng đời | Có vòng đời riêng | Thường phụ thuộc vào Entity hoặc thao tác sử dụng nó |
| Ví dụ | Sách, Độc giả, Phiếu mượn | ISBN, Địa chỉ, Khoảng thời gian, Money |

Không thể quyết định Entity hay Value Object chỉ dựa vào tên gọi hoặc việc một lớp có được lưu trong bảng cơ sở dữ liệu hay không. Câu hỏi cần đặt ra là: miền nghiệp vụ có cần phân biệt từng cá thể qua thời gian không? Nếu có, khái niệm đó thường cần identity. Nếu chỉ quan tâm đến giá trị mà nó biểu diễn, Value Object thường phù hợp hơn.

Ví dụ, địa chỉ giao hàng thường là Value Object vì hệ thống quan tâm đến các thành phần địa chỉ. Nhưng nếu doanh nghiệp quản lý một địa điểm giao nhận như một thực thể có mã riêng, lịch sử hoạt động và trạng thái, địa điểm đó có thể là Entity. Cùng một khái niệm ngoài đời có thể được mô hình hóa khác nhau tùy mục tiêu và quy tắc của hệ thống.

## 5. Quy tắc bất biến (Invariant)

Invariant là điều kiện phải luôn đúng đối với một đối tượng hoặc một phạm vi nghiệp vụ trong mọi trạng thái hợp lệ. Mọi thao tác làm thay đổi trạng thái phải giữ invariant đúng sau khi hoàn tất.

Ví dụ trong hệ thống thư viện:

- Tiêu đề sách không được để trống.
- ISBN của một cuốn sách phải có định dạng hợp lệ.
- Số lượng bản sao khả dụng không được âm.
- Một phiếu mượn không thể được đánh dấu đã trả nếu chưa từng được mượn.
- Một khoản tiền phải gắn với đơn vị tiền tệ.

Invariant là cam kết của mô hình nghiệp vụ. Nó khác với một thông báo lỗi trên biểu mẫu: thông báo có thể thay đổi theo giao diện và ngôn ngữ, còn invariant phải được giữ đúng dù thao tác đến từ trang web, API, tác vụ nền hay một đoạn mã nội bộ.

### Invariant ở các phạm vi khác nhau

**Invariant của một đối tượng** có thể được kiểm tra ngay bên trong Entity hoặc Value Object. Ví dụ, tiêu đề sách không rỗng và ISBN có cấu trúc hợp lệ. Constructor, factory và các phương thức thay đổi trạng thái là nơi phù hợp để bảo vệ các điều kiện này.

**Invariant của một nhóm đối tượng liên quan** có thể cần được bảo vệ tại một ranh giới nhất quán (thường được mô hình hóa bằng Aggregate trong Domain-Driven Design). Ví dụ, một phiếu mượn quản lý các dòng mượn và không cho phép cùng một cuốn sách xuất hiện hai lần trong phiếu đó. Aggregate Root điều phối thay đổi để các điều kiện trong phạm vi được giữ đúng.

**Quy tắc phụ thuộc dữ liệu hoặc nhiều giao dịch** thường cần Service, Repository và ràng buộc cơ sở dữ liệu phối hợp. Ví dụ, ISBN phải duy nhất trong toàn bộ danh mục. Một lần kiểm tra `existsByIsbn` trước khi insert có thể cải thiện thông báo nghiệp vụ, nhưng hai request đồng thời vẫn có thể vượt qua bước kiểm tra. Unique constraint ở cơ sở dữ liệu là lớp bảo vệ cuối cùng để bảo đảm tính duy nhất.

Không nên đặt mọi quy tắc vào một Entity duy nhất. Hãy đặt invariant tại nơi có đủ thông tin và có thể bảo vệ nó một cách nhất quán; với quy tắc liên quan nhiều đối tượng hoặc nhiều giao dịch, cần một ranh giới nghiệp vụ và cơ chế lưu trữ phù hợp.

## 6. Kết hợp Entity, Value Object và Invariant trong Model

Xét chức năng tạo sách mới. Người dùng nhập tiêu đề và ISBN. Hệ thống cần đảm bảo tiêu đề có nội dung, ISBN hợp lệ và ISBN chưa được sử dụng.

Luồng trách nhiệm có thể được tổ chức như sau:

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as BookController
    participant S as BookService
    participant E as Book Entity
    participant V as Isbn Value Object
    participant R as BookRepository
    U->>C: POST /books
    C->>C: Bind và kiểm tra form
    C->>S: createBook(title, isbnText)
    S->>V: Tạo Isbn từ chuỗi
    V-->>S: Isbn hợp lệ hoặc lỗi
    S->>R: Kiểm tra ISBN đã tồn tại
    R-->>S: Kết quả kiểm tra
    S->>E: Tạo Book với ID và Isbn
    E-->>S: Book hợp lệ
    S->>R: Lưu Book
    R-->>S: Kết quả lưu
    S-->>C: Kết quả use case
    C-->>U: Redirect hoặc lỗi biểu mẫu
~~~

Trong luồng này, mỗi thành phần có một trách nhiệm:

1. **Controller** tiếp nhận HTTP request, binding dữ liệu và chọn response.
2. **Form/Request DTO** mô tả dữ liệu đầu vào của giao diện; nó có thể kiểm tra các lỗi định dạng cơ bản để phản hồi thân thiện.
3. **Value Object `Isbn`** chuẩn hóa và bảo vệ định dạng ISBN ở cấp miền.
4. **Entity `Book`** giữ identity và các invariant của một cuốn sách, chẳng hạn tiêu đề không rỗng.
5. **BookService** điều phối use case và các quy tắc cần phối hợp với kho dữ liệu.
6. **BookRepository** lưu và truy vấn Entity; cơ sở dữ liệu áp dụng unique constraint cho ISBN.

Đây là một cách phân chia trách nhiệm có thể dùng trong ứng dụng MVC; không phải mọi dự án đều cần một lớp riêng cho từng bước. Quy mô và độ phức tạp của miền nghiệp vụ quyết định mức độ tách lớp.

### Ví dụ service điều phối

~~~java
public class BookService {
    private final BookRepository books;

    public BookService(BookRepository books) {
        this.books = books;
    }

    public Book createBook(String title, String isbnText) {
        Isbn isbn = new Isbn(isbnText);

        if (books.existsByIsbn(isbn)) {
            throw new DuplicateIsbnException(isbn);
        }

        Book book = Book.create(UUID.randomUUID(), isbn, title);
        return books.save(book);
    }
}
~~~

Đoạn mã minh họa vai trò điều phối, giả định `BookRepository` và `DuplicateIsbnException` đã được định nghĩa. Trong triển khai thực tế, thao tác kiểm tra trùng và lưu cần nằm trong transaction thích hợp, đồng thời cơ sở dữ liệu phải có unique constraint. Service cần chuyển lỗi vi phạm constraint thành lỗi nghiệp vụ phù hợp để Controller trả phản hồi có thể hiểu được.

## 7. Invariant khác gì validation của biểu mẫu?

Validation ở tầng giao diện và invariant của Model có liên quan nhưng không thay thế nhau.

| Khía cạnh | Validation đầu vào | Invariant của Model |
|---|---|---|
| Mục đích | Giúp người dùng gửi dữ liệu đúng định dạng và nhận lỗi dễ hiểu | Bảo đảm trạng thái nghiệp vụ luôn hợp lệ |
| Vị trí thường gặp | Form, Request DTO, Controller binding | Entity, Value Object, Aggregate hoặc Service theo phạm vi quy tắc |
| Nguồn dữ liệu | Dữ liệu đến từ một request cụ thể | Mọi nguồn có thể làm thay đổi miền nghiệp vụ |
| Có thể bỏ qua không? | Có thể có luồng khác không đi qua form đó | Không được bỏ qua khi tạo hoặc thay đổi trạng thái thuộc phạm vi bảo vệ |

Ví dụ, form tạo sách có thể khai báo `@NotBlank` cho trường tiêu đề để hiển thị lỗi ngay trên trang. Nhưng `Book` vẫn phải từ chối tiêu đề rỗng, bởi sách có thể được tạo qua API hoặc tác vụ nhập dữ liệu không dùng form này.

Ngược lại, không phải mọi quy tắc đều nên lặp lại ở Entity. Quy tắc như chuỗi tìm kiếm tối đa 100 ký tự có thể chỉ là giới hạn giao diện hoặc API. Chỉ đưa nó thành invariant miền khi nghiệp vụ thực sự yêu cầu mọi giá trị được lưu phải tuân thủ giới hạn đó.

## 8. Phân biệt Domain Model với DTO và Persistence Model

Trong ứng dụng MVC, từ “Model” thường được dùng cho nhiều loại đối tượng khác nhau. Nếu không phân biệt, mã nguồn dễ biến Entity thành túi dữ liệu được chia sẻ giữa Controller, View và cơ sở dữ liệu.

| Loại đối tượng | Vai trò | Ví dụ |
|---|---|---|
| Domain Entity | Biểu diễn khái niệm có identity và hành vi nghiệp vụ | `Book` |
| Value Object | Biểu diễn một giá trị có quy tắc và phép so sánh theo giá trị | `Isbn`, `Money` |
| Form/Request DTO | Mang dữ liệu người dùng gửi lên | `CreateBookForm` |
| View Model/Response DTO | Mang dữ liệu đã chọn để trình bày hoặc trả về client | `BookDetailView` |
| Persistence Model | Phục vụ ánh xạ và lưu trữ theo cấu trúc dữ liệu | JPA entity hoặc document lưu trữ |

Những loại đối tượng này có thể trùng nhau trong ứng dụng nhỏ, nhưng chúng có mục tiêu khác nhau. Domain Entity bảo vệ quy tắc nghiệp vụ; Request DTO phản ánh hợp đồng đầu vào; View Model phản ánh dữ liệu cần trình bày; Persistence Model phản ánh cách lưu trữ. Khi các yêu cầu thay đổi độc lập, tách chúng ra giúp giảm phụ thuộc và tránh đưa dữ liệu nội bộ hoặc trường nhạy cảm lên View.

Ví dụ, `CreateBookForm` có thể chứa `title` và `isbn` dưới dạng chuỗi. Service chuyển chúng thành `Book` và `Isbn`. Khi hiển thị trang chi tiết, Controller có thể chuyển Entity thành `BookDetailView` chỉ gồm `id`, `title` và `isbn`. View không cần biết cách Entity được lưu trong cơ sở dữ liệu.

## 9. Kiểm thử Entity, Value Object và Invariant

Ranh giới rõ ràng giúp kiểm thử Model mà không cần khởi động toàn bộ ứng dụng web.

**Kiểm thử Value Object:** xác minh chuẩn hóa, giá trị hợp lệ, giá trị không hợp lệ và phép so sánh theo giá trị. Ví dụ hai ISBN có dấu gạch nối và không có dấu gạch nối phải tương đương sau chuẩn hóa.

**Kiểm thử Entity:** xác minh identity không đổi khi thuộc tính thay đổi, hành vi cập nhật đúng, và thao tác vi phạm invariant bị từ chối. Ví dụ đổi tiêu đề hợp lệ thành công, nhưng đổi thành chuỗi trắng phải phát sinh lỗi.

**Kiểm thử Service hoặc Aggregate:** xác minh quy tắc cần phối hợp nhiều đối tượng hoặc kho dữ liệu, như không tạo sách với ISBN đã tồn tại hoặc không thêm trùng một cuốn sách vào phiếu mượn.

**Kiểm thử tích hợp với cơ sở dữ liệu:** xác minh unique constraint và transaction thực sự bảo vệ dữ liệu khi có xung đột. Unit test kiểm tra lời gọi repository không đủ để chứng minh cơ sở dữ liệu ngăn được hai request đồng thời tạo cùng ISBN.

Một số ca kiểm thử tiêu biểu:

| Thành phần | Tình huống | Kết quả mong đợi |
|---|---|---|
| `Isbn` | Chuỗi ISBN hợp lệ có dấu gạch nối | Chuẩn hóa thành dạng thống nhất |
| `Isbn` | Chuỗi rỗng hoặc sai cấu trúc | Từ chối tạo Value Object |
| `Book` | Tạo sách với tiêu đề hợp lệ | Tạo Entity có identity |
| `Book` | Đổi tiêu đề thành chuỗi trắng | Không cho trạng thái không hợp lệ |
| `Book` | Đổi tiêu đề nhưng giữ nguyên ID | Vẫn là cùng Entity |
| `BookService` | ISBN đã tồn tại | Trả lỗi nghiệp vụ phù hợp |
| Database | Hai giao dịch đồng thời lưu cùng ISBN | Unique constraint chỉ cho phép một giá trị duy nhất |

## 10. Những sai lầm thường gặp

- **Dùng mọi lớp dữ liệu làm Entity.** Một đối tượng chỉ chứa giá trị như ISBN hoặc Money thường phù hợp với Value Object hơn nếu không có identity riêng.
- **So sánh Entity bằng tất cả thuộc tính.** Nếu tiêu đề hoặc trạng thái thay đổi, phép bằng nhau theo toàn bộ thuộc tính có thể khiến một Entity bị xem nhầm là đối tượng khác.
- **Để Value Object có thể thay đổi tùy ý.** Thay đổi giá trị tại chỗ làm đối tượng khác đang tham chiếu đến nó bị ảnh hưởng khó đoán. Hãy tạo giá trị mới.
- **Chỉ kiểm tra dữ liệu ở Controller.** Các luồng khác có thể bỏ qua Controller; invariant cần được bảo vệ ở Model hoặc ranh giới nghiệp vụ thích hợp.
- **Đặt mọi quy tắc trong constructor.** Constructor phù hợp với invariant của đối tượng, nhưng quy tắc cần truy vấn nhiều Entity hoặc phối hợp giao dịch thường thuộc Service, Aggregate hay cơ sở dữ liệu.
- **Nhầm invariant với constraint của giao diện.** Chỉ những điều kiện thuộc tính đúng đắn của miền mới cần được bảo vệ như invariant nghiệp vụ.
- **Cho View truy cập trực tiếp Entity và mọi trường dữ liệu.** Điều này tạo phụ thuộc vào mô hình lưu trữ và có thể làm lộ dữ liệu không cần thiết; hãy cân nhắc View Model hoặc DTO.

## 11. Kết luận

Entity giúp Model biểu diễn những đối tượng có identity và vòng đời riêng. Value Object biểu diễn các giá trị được nhận diện bằng nội dung của chúng và thường nên bất biến. Invariant xác định những điều kiện phải luôn đúng để trạng thái nghiệp vụ hợp lệ.

Khi thiết kế Model trong MVC, hãy xác định đối tượng nào cần identity, giá trị nào nên là Value Object, và mỗi invariant thuộc phạm vi một đối tượng, một nhóm đối tượng hay toàn bộ dữ liệu cần được bảo vệ ở đâu. Đặt quy tắc tại đúng ranh giới giúp ứng dụng giữ dữ liệu nhất quán dù request đến từ biểu mẫu web, API hay tác vụ nền.
