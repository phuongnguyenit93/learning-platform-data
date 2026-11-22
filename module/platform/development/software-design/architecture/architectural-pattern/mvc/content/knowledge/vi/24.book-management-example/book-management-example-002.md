# Xác định Model và quy tắc nghiệp vụ

Khi xây dựng một ứng dụng quản lý sách theo MVC, bước đầu tiên không phải là tạo một lớp cho mỗi bảng cơ sở dữ liệu. Trước hết cần hiểu ứng dụng quản lý điều gì, người dùng được phép làm gì và những điều kiện nào phải luôn đúng. Từ đó mới xác định các đối tượng, trạng thái, quan hệ và hành vi cần có trong Model.

Một lỗi thường gặp là tạo một lớp Book chỉ chứa ISBN, tiêu đề, tác giả, giá và số lượng, sau đó để Controller hoặc Service tự sửa các trường. Cách này có thể đáp ứng CRUD ban đầu, nhưng quy tắc như ISBN phải duy nhất, số lượng không được âm, sách đã ngừng kinh doanh không được nhập kho hoặc không thể thay đổi giá theo một số trạng thái sẽ bị phân tán.

Bài học này dùng một ví dụ quản lý danh mục sách và số lượng tồn kho. Phạm vi minh họa tập trung vào đăng ký đầu sách, cập nhật thông tin, thay đổi giá, nhập/xuất kho và lưu trữ đầu sách. Chức năng mượn/trả sách của thư viện là một nghiệp vụ khác; nếu có, nên mô hình hóa thêm Member, Loan và các quy tắc thời hạn thay vì nhồi toàn bộ vòng đời mượn trả vào Book.

## 1. Mục tiêu

Sau bài học, bạn có thể:

- Phân tích yêu cầu quản lý sách thành các khái niệm và hành động nghiệp vụ.
- Phân biệt đầu sách với từng bản sao vật lý hoặc số lượng tồn kho.
- Xác định Entity, Value Object, trạng thái và Aggregate Root.
- Viết các bất biến như ISBN hợp lệ, giá không âm và tồn kho không âm.
- Phân biệt quy tắc nằm trong Domain Model với quy tắc cần Repository hoặc Application Service.
- Thiết kế các use case tạo sách, cập nhật thông tin, nhập kho, xuất kho và lưu trữ.
- Tách Request DTO, Domain Model, Persistence Entity và View Model.
- Kết nối Model với Controller, Application Service và Repository trong MVC.
- Kiểm thử quy tắc nghiệp vụ độc lập với HTTP và database.

## 2. Xác định phạm vi và ngôn ngữ nghiệp vụ

Trước khi viết code, hãy thống nhất ứng dụng đang quản lý loại đối tượng nào.

Trong ví dụ này:

- **Đầu sách (Book):** một ấn bản được nhận diện bằng ISBN, có tiêu đề, tác giả, nhà xuất bản và năm xuất bản.
- **Tồn kho (Stock):** số lượng bản của đầu sách hiện có trong kho.
- **Giá bán (Price):** giá hiện hành dùng cho nghiệp vụ bán hàng trong ví dụ.
- **Trạng thái (Status):** đầu sách đang kinh doanh hay đã lưu trữ.
- **Nhập kho (Receive Stock):** tăng số lượng có sẵn.
- **Xuất kho (Remove Stock):** giảm số lượng có sẵn sau một thao tác nghiệp vụ hợp lệ.
- **Lưu trữ (Archive):** ngừng kinh doanh đầu sách nhưng vẫn giữ lịch sử.

Ở đây, Book đại diện cho đầu sách và một số lượng tồn kho tổng hợp. Nếu cần quản lý từng cuốn sách với mã vạch, vị trí kệ, tình trạng vật lý hoặc lịch sử mượn, cần bổ sung một mô hình Copy/BookCopy riêng. Không nên dùng một trường quantity để giả lập định danh của từng bản sao khi nghiệp vụ cần theo dõi từng cuốn.

### 2.1. Tác nhân và mục tiêu

| Tác nhân | Mục tiêu | Hành động điển hình |
|---|---|---|
| Nhân viên danh mục | Quản lý thông tin đầu sách | Tạo, sửa tiêu đề, tác giả, nhà xuất bản |
| Nhân viên kho | Theo dõi số lượng | Nhập kho, xuất kho, kiểm kê |
| Quản lý | Kiểm soát hoạt động kinh doanh | Đổi giá, lưu trữ, khôi phục đầu sách |
| Người xem | Tra cứu danh mục | Tìm theo ISBN, tiêu đề, tác giả |

Vai trò ở bảng trên mô tả nghiệp vụ. Quyền thực tế của từng người cần được kiểm tra ở application/security layer. Không nên để Domain Model phụ thuộc trực tiếp vào session hoặc Spring Security.

### 2.2. Liệt kê use case trước khi thiết kế lớp

Các use case chính của ví dụ:

1. Đăng ký một đầu sách mới.
2. Cập nhật metadata của đầu sách.
3. Thay đổi giá bán.
4. Nhập thêm số lượng vào kho.
5. Xuất một số lượng khỏi kho.
6. Lưu trữ đầu sách.
7. Khôi phục đầu sách đã lưu trữ.
8. Tra cứu và xem danh sách đầu sách.

Việc liệt kê hành động giúp tìm ra hành vi cần có trong Model. Nếu chỉ nhìn vào danh sách cột, ta dễ tạo ra một lớp dữ liệu thụ động mà không nhận ra các quy tắc chuyển trạng thái.

## 3. Chuyển yêu cầu thành quy tắc nghiệp vụ

Một yêu cầu như “quản lý sách” còn quá rộng. Cần chuyển nó thành các điều kiện có thể kiểm tra.

### 3.1. Quy tắc dữ liệu đầu sách

- ISBN phải có định dạng hợp lệ.
- ISBN không được trùng với đầu sách khác.
- Tiêu đề không được để trống.
- Phải có ít nhất một tác giả.
- Năm xuất bản phải nằm trong phạm vi hợp lý.
- Nhà xuất bản phải có giá trị nếu nghiệp vụ yêu cầu.
- Giá bán không được âm.
- Tiền tệ của giá phải được xác định rõ.

### 3.2. Quy tắc tồn kho

- Số lượng tồn kho không được âm.
- Số lượng nhập kho phải lớn hơn 0.
- Số lượng xuất kho phải lớn hơn 0.
- Không được xuất nhiều hơn số lượng hiện có.
- Không được nhập hoặc xuất kho cho đầu sách đã lưu trữ.
- Phép cộng số lượng phải phát hiện tràn số nguyên.

### 3.3. Quy tắc trạng thái

Ví dụ chính sách:

- Đầu sách mới được đăng ký ở trạng thái ACTIVE.
- Chỉ đầu sách ACTIVE mới được đổi giá hoặc thay đổi tồn kho.
- Chỉ đầu sách có tồn kho bằng 0 mới được lưu trữ.
- Đầu sách ARCHIVED không được bán hoặc nhập kho.
- Đầu sách ARCHIVED có thể được khôi phục bằng thao tác có quyền.

Đây là lựa chọn nghiệp vụ của ví dụ, không phải quy tắc bắt buộc cho mọi ứng dụng. Một hệ thống có thể cho phép lưu trữ khi còn tồn kho nếu có quy trình thanh lý riêng. Điều quan trọng là phải thống nhất chính sách và mã hóa nó thành hành vi rõ ràng.

### 3.4. Quy tắc cần kiểm tra ngoài một Book

Một số quy tắc không thể được quyết định chỉ bằng trạng thái của một đối tượng:

- ISBN có duy nhất trong toàn bộ danh mục hay không?
- Người dùng hiện tại có quyền đổi giá không?
- Kho nào được phép nhập/xuất đầu sách?
- Một lệnh xuất kho có đang được gửi lặp không?
- Dữ liệu có bị thay đổi bởi request khác trong lúc xử lý không?

Các điều kiện này cần Repository, Application Service, authorization policy hoặc database constraint. Không ép mọi quy tắc vào một phương thức của Book.

## 4. Chọn Model từ khái niệm nghiệp vụ

Với phạm vi hiện tại, mô hình cốt lõi có thể gồm:

| Thành phần | Vai trò | Vì sao cần |
|---|---|---|
| Book | Entity/Aggregate Root | Có định danh và quản lý trạng thái đầu sách |
| BookId | Value Object | Định danh đầu sách có kiểu rõ ràng |
| Isbn13 | Value Object | Chuẩn hóa và xác thực ISBN |
| AuthorName | Value Object | Biểu diễn tên tác giả đã được kiểm tra |
| Money | Value Object | Giá trị tiền tệ và quy tắc so sánh |
| BookStatus | Enum | Trạng thái được phép |
| BookRepository | Port | Tìm và lưu aggregate |
| BookQueries | Query service | Đọc danh sách/chi tiết theo nhu cầu giao diện |

Không nhất thiết tạo Entity riêng cho Author nếu ứng dụng chỉ lưu tên tác giả như một thuộc tính của đầu sách. Nếu tác giả có hồ sơ độc lập, bút danh, tiểu sử, quan hệ nhiều đầu sách và quy trình quản lý riêng, lúc đó có thể tạo Author aggregate và tham chiếu bằng AuthorId.

Tương tự, nhà xuất bản có thể chỉ là một tên trong mô hình nhỏ. Khi cần quản lý hợp đồng, địa chỉ, người liên hệ hoặc trạng thái nhà xuất bản, nó có thể trở thành một khái niệm có vòng đời riêng.

## 5. Phân biệt Entity và Value Object

Book là Entity vì mỗi đầu sách có một BookId ổn định. Hai đầu sách có cùng tiêu đề và tác giả vẫn có thể là hai bản ghi khác nhau nếu ISBN hoặc định danh khác nhau.

ISBN, tên tác giả và tiền là những giá trị có thể được mô hình hóa thành Value Object. Chúng không cần identity riêng trong phạm vi ví dụ; ý nghĩa nằm ở giá trị và các quy tắc của giá trị đó.

### 5.1. BookId

~~~java
public record BookId(UUID value) {
    public BookId {
        Objects.requireNonNull(value, "Book ID is required");
    }

    public static BookId newId() {
        return new BookId(UUID.randomUUID());
    }
}
~~~

Dùng BookId thay vì truyền UUID khắp nơi giúp compiler phân biệt ID của sách với ID của người dùng hoặc nhà xuất bản.

### 5.2. Isbn13

Ví dụ này chọn ISBN-13 để minh họa. Value Object chuẩn hóa dấu cách/gạch nối và kiểm tra chữ số kiểm tra:

~~~java
public record Isbn13(String value) {
    public Isbn13 {
        Objects.requireNonNull(value, "ISBN is required");

        String normalized = value.replaceAll("[\\s-]", "");

        if (!normalized.matches("\\d{13}")) {
            throw new IllegalArgumentException(
                "ISBN must contain 13 digits"
            );
        }

        int sum = 0;
        for (int index = 0; index < 12; index++) {
            int digit = Character.digit(normalized.charAt(index), 10);
            sum += digit * (index % 2 == 0 ? 1 : 3);
        }

        int expectedCheckDigit = (10 - (sum % 10)) % 10;
        int actualCheckDigit =
            Character.digit(normalized.charAt(12), 10);

        if (actualCheckDigit != expectedCheckDigit) {
            throw new IllegalArgumentException(
                "ISBN check digit is invalid"
            );
        }

        value = normalized;
    }
}
~~~

Kiểm tra checksum giúp phát hiện nhiều lỗi nhập liệu, nhưng không chứng minh ISBN đã được cấp hợp lệ hoặc thuộc đúng đầu sách. Nếu hệ thống cần xác minh dữ liệu thư mục, cần nguồn dữ liệu hoặc quy trình nghiệp vụ riêng.

### 5.3. AuthorName

~~~java
public record AuthorName(String value) {
    public AuthorName {
        Objects.requireNonNull(value, "Author name is required");
        value = value.trim();

        if (value.isBlank()) {
            throw new IllegalArgumentException(
                "Author name must not be blank"
            );
        }

        if (value.length() > 150) {
            throw new IllegalArgumentException(
                "Author name is too long"
            );
        }
    }
}
~~~

Value Object giữ quy tắc chuẩn hóa ở một nơi. Nếu nhiều đầu sách dùng cùng tác giả nhưng cần quản lý danh tính tác giả, không nên xem AuthorName là thay thế cho Author aggregate.

### 5.4. Money

Không dùng double cho tiền vì biểu diễn nhị phân có thể gây sai số. Dùng BigDecimal và Currency:

~~~java
public record Money(BigDecimal amount, Currency currency)
        implements Comparable<Money> {

    public Money {
        Objects.requireNonNull(amount);
        Objects.requireNonNull(currency);

        if (amount.signum() < 0) {
            throw new IllegalArgumentException(
                "Price must not be negative"
            );
        }

        int scale = Math.max(currency.getDefaultFractionDigits(), 0);
        amount = amount.setScale(scale, RoundingMode.HALF_UP);
    }

    public static Money of(BigDecimal amount, Currency currency) {
        return new Money(amount, currency);
    }

    @Override
    public int compareTo(Money other) {
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException(
                "Cannot compare different currencies"
            );
        }
        return amount.compareTo(other.amount);
    }
}
~~~

Ví dụ dùng quy tắc làm tròn minh họa. Chính sách tiền tệ thực tế phải được thống nhất với nghiệp vụ và hệ thống kế toán. Không nên giả định mọi loại tiền đều có cùng scale hoặc mọi phép tính đều được làm tròn ở cùng một thời điểm.

## 6. Xác định trạng thái của Book

Trạng thái biểu diễn giai đoạn vòng đời mà một đầu sách đang ở. Dùng enum giúp giới hạn tập giá trị:

~~~java
public enum BookStatus {
    ACTIVE,
    ARCHIVED
}
~~~

Không nên lưu trạng thái tùy ý dưới dạng String rồi so sánh rải rác. Enum và hành vi domain làm rõ những chuyển đổi được phép. Nếu quy trình sau này có thêm trạng thái như PENDING_REVIEW hoặc DISCONTINUED, cần xác định ý nghĩa và các cạnh chuyển trạng thái trước khi thêm vào enum.

### 6.1. State transition

Trong ví dụ:

~~~mermaid
stateDiagram-v2
    [*] --> ACTIVE: register
    ACTIVE --> ARCHIVED: archive / stock = 0
    ARCHIVED --> ACTIVE: restore
~~~

Một đầu sách không được chuyển thẳng từ trạng thái bất kỳ sang trạng thái khác chỉ vì request gửi lên một giá trị enum. Client gửi hành động như archive hoặc restore; Domain Model quyết định trạng thái mới.

## 7. Book là Aggregate Root

Book quản lý thông tin đầu sách, giá, tồn kho và trạng thái. Bên ngoài không được tùy ý sửa các trường này; thay đổi phải đi qua các phương thức có tên nghiệp vụ.

~~~java
public final class Book {
    private final BookId id;
    private final Isbn13 isbn;
    private String title;
    private List<AuthorName> authors;
    private String publisher;
    private int publicationYear;
    private Money price;
    private int stockQuantity;
    private BookStatus status;

    private Book(
            BookId id,
            Isbn13 isbn,
            String title,
            List<AuthorName> authors,
            String publisher,
            int publicationYear,
            Money price,
            int stockQuantity) {

        this.id = Objects.requireNonNull(id);
        this.isbn = Objects.requireNonNull(isbn);
        String normalizedTitle = requireText(title, "Title");
        List<AuthorName> validatedAuthors = validateAuthors(authors);
        String normalizedPublisher = requireText(publisher, "Publisher");

        this.title = normalizedTitle;
        this.authors = validatedAuthors;
        this.publisher = normalizedPublisher;
        this.publicationYear = publicationYear;
        this.price = Objects.requireNonNull(price);
        this.stockQuantity = requireNonNegative(stockQuantity);
        this.status = BookStatus.ACTIVE;
    }

    public static Book register(
            BookId id,
            Isbn13 isbn,
            String title,
            List<AuthorName> authors,
            String publisher,
            int publicationYear,
            Money price,
            int initialStock,
            int currentYear) {

        if (publicationYear < 1450 || publicationYear > currentYear + 1) {
            throw new BookRuleViolation(
                "Publication year is outside the allowed range"
            );
        }

        return new Book(
            id, isbn, title, authors, publisher,
            publicationYear, price, initialStock
        );
    }

    public static Book reconstitute(
            BookId id,
            Isbn13 isbn,
            String title,
            List<AuthorName> authors,
            String publisher,
            int publicationYear,
            Money price,
            int stockQuantity,
            BookStatus status,
            int currentYear) {

        Book book = register(
            id, isbn, title, authors, publisher,
            publicationYear, price, stockQuantity, currentYear
        );
        Objects.requireNonNull(status);

        if (status == BookStatus.ARCHIVED && stockQuantity != 0) {
            throw new BookRuleViolation(
                "An archived book cannot have stock"
            );
        }

        book.status = status;
        return book;
    }

    public void changeMetadata(
            String title,
            List<AuthorName> authors,
            String publisher,
            int publicationYear,
            int currentYear) {

        requireActive();

        if (publicationYear < 1450 || publicationYear > currentYear + 1) {
            throw new BookRuleViolation(
                "Publication year is outside the allowed range"
            );
        }

        String normalizedTitle = requireText(title, "Title");
        List<AuthorName> validatedAuthors = validateAuthors(authors);
        String normalizedPublisher = requireText(publisher, "Publisher");

        this.title = normalizedTitle;
        this.authors = validatedAuthors;
        this.publisher = normalizedPublisher;
        this.publicationYear = publicationYear;
    }

    public void changePrice(Money newPrice) {
        requireActive();
        Objects.requireNonNull(newPrice);

        if (!price.currency().equals(newPrice.currency())) {
            throw new BookRuleViolation(
                "Book price currency cannot be changed"
            );
        }

        this.price = newPrice;
    }

    public void receiveStock(int quantity) {
        requireActive();
        requirePositive(quantity, "Received quantity");
        try {
            this.stockQuantity = Math.addExact(stockQuantity, quantity);
        } catch (ArithmeticException exception) {
            throw new BookRuleViolation(
                "Stock quantity exceeds the supported limit"
            );
        }
    }

    public void removeStock(int quantity) {
        requireActive();
        requirePositive(quantity, "Removed quantity");

        if (quantity > stockQuantity) {
            throw new BookRuleViolation(
                "Not enough stock available"
            );
        }

        stockQuantity -= quantity;
    }

    public void archive() {
        requireActive();

        if (stockQuantity != 0) {
            throw new BookRuleViolation(
                "A book can be archived only when stock is zero"
            );
        }

        status = BookStatus.ARCHIVED;
    }

    public void restore() {
        if (status != BookStatus.ARCHIVED) {
            throw new BookRuleViolation(
                "Only an archived book can be restored"
            );
        }

        status = BookStatus.ACTIVE;
    }

    private void requireActive() {
        if (status != BookStatus.ACTIVE) {
            throw new BookRuleViolation(
                "The book is not active"
            );
        }
    }

    private static String requireText(String value, String field) {
        Objects.requireNonNull(value, field + " is required");
        String normalized = value.trim();

        if (normalized.isBlank()) {
            throw new BookRuleViolation(field + " must not be blank");
        }

        return normalized;
    }

    private static List<AuthorName> validateAuthors(
            List<AuthorName> authors) {
        Objects.requireNonNull(authors);

        if (authors.isEmpty()) {
            throw new BookRuleViolation(
                "A book must have at least one author"
            );
        }

        return List.copyOf(authors);
    }

    private static int requireNonNegative(int value) {
        if (value < 0) {
            throw new BookRuleViolation(
                "Stock quantity must not be negative"
            );
        }
        return value;
    }

    private static void requirePositive(int value, String field) {
        if (value <= 0) {
            throw new BookRuleViolation(
                field + " must be positive"
            );
        }
    }

    public BookId id() { return id; }
    public Isbn13 isbn() { return isbn; }
    public String title() { return title; }
    public List<AuthorName> authors() { return List.copyOf(authors); }
    public String publisher() { return publisher; }
    public int publicationYear() { return publicationYear; }
    public Money price() { return price; }
    public int stockQuantity() { return stockQuantity; }
    public BookStatus status() { return status; }
}
~~~

Ví dụ giả định các import và exception phụ trợ đã được khai báo. ISBN được giữ bất biến sau khi đăng ký; nếu cần sửa ISBN do nhập sai, hãy thiết kế một use case hiệu chỉnh có kiểm tra trùng và audit rõ ràng thay vì mở setter công khai.

Exception dùng để biểu diễn vi phạm quy tắc của ví dụ:

~~~java
public final class BookRuleViolation extends RuntimeException {
    public BookRuleViolation(String message) {
        super(message);
    }
}
~~~

Các bước chuẩn hóa trong changeMetadata được thực hiện vào biến cục bộ trước khi gán vào Book. Nếu một trường không hợp lệ, aggregate giữ nguyên trạng thái cũ thay vì bị cập nhật một phần.

### 7.1. Những bất biến được bảo vệ

| Bất biến | Nơi bảo vệ | Lý do |
|---|---|---|
| ISBN có cấu trúc hợp lệ | Isbn13 | Quy tắc của giá trị ISBN |
| Tiêu đề không rỗng | Book | Metadata bắt buộc của đầu sách |
| Có ít nhất một tác giả | Book | Quy tắc đăng ký trong ví dụ |
| Giá không âm | Money | Quy tắc giá trị tiền |
| Tiền tệ của giá không đổi sau đăng ký | Book | Tránh trộn giá của cùng đầu sách giữa các tiền tệ |
| Tồn kho không âm | Book | Quy tắc trạng thái aggregate |
| Chỉ nhập/xuất khi ACTIVE | Book | Quy tắc vòng đời |
| Không xuất quá tồn kho | Book | Bảo vệ số lượng |
| Chỉ lưu trữ khi tồn kho bằng 0 | Book | Quy tắc chuyển trạng thái |

### 7.2. Vì sao không cung cấp setter?

Nếu có setStockQuantity(-5) hoặc setStatus(ARCHIVED), bất kỳ Controller hay Service nào cũng có thể bỏ qua quy tắc. Các phương thức receiveStock, removeStock và archive diễn đạt ý định nghiệp vụ, đồng thời bảo vệ điều kiện cần thiết.

Các getter trả về bản sao bất biến của danh sách tác giả để bên ngoài không thể sửa collection nội bộ mà không qua changeMetadata.

## 8. Quy tắc duy nhất của ISBN thuộc nhiều đối tượng

Book có thể xác thực định dạng ISBN nhưng không thể tự biết ISBN đó đã được một Book khác sử dụng hay chưa. Quy tắc duy nhất cần truy vấn Repository và được bảo vệ cuối cùng bởi database.

Hợp đồng Repository:

~~~java
public interface BookRepository {
    Optional<Book> findById(BookId id);
    boolean existsByIsbn(Isbn13 isbn);
    void save(Book book);
}
~~~

Use case đăng ký sách kiểm tra trước khi lưu:

~~~java
public record RegisterBookCommand(
    String isbn,
    String title,
    List<String> authors,
    String publisher,
    int publicationYear,
    BigDecimal price,
    String currencyCode,
    int initialStock
) {}
~~~

~~~java
public class RegisterBookService {
    private final BookRepository books;
    private final Clock clock;

    public RegisterBookService(BookRepository books, Clock clock) {
        this.books = books;
        this.clock = clock;
    }

    @Transactional
    public BookId handle(RegisterBookCommand command) {
        Isbn13 isbn = new Isbn13(command.isbn());

        if (books.existsByIsbn(isbn)) {
            throw new DuplicateIsbnException(isbn.value());
        }

        List<AuthorName> authors = command.authors().stream()
            .map(AuthorName::new)
            .toList();

        Money price = Money.of(
            command.price(),
            Currency.getInstance(command.currencyCode())
        );

        Book book = Book.register(
            BookId.newId(),
            isbn,
            command.title(),
            authors,
            command.publisher(),
            command.publicationYear(),
            price,
            command.initialStock(),
            Year.now(clock).getValue()
        );

        books.save(book);
        return book.id();
    }
}
~~~

Kiểm tra existsByIsbn trước khi lưu cải thiện thông báo cho người dùng, nhưng không loại bỏ race condition: hai request có thể cùng kiểm tra “chưa tồn tại” rồi cùng insert. Database cần unique constraint trên ISBN; adapter phải chuyển lỗi unique violation thành DuplicateIsbnException hoặc lỗi ứng dụng tương ứng.

Đây là ví dụ minh họa. Annotation @Transactional được đặt ở application boundary để việc kiểm tra và lưu nằm trong một transaction; unique constraint của database vẫn cần thiết vì transaction thông thường không tự loại bỏ mọi race condition. Không để Domain Model gọi trực tiếp database chỉ để kiểm tra uniqueness.

## 9. Tách quy tắc Domain và quy tắc Application

Không phải mọi điều kiện đều thuộc Book.

| Quy tắc | Nơi phù hợp | Giải thích |
|---|---|---|
| ISBN-13 có checksum hợp lệ | Isbn13 | Chỉ phụ thuộc giá trị ISBN |
| Giá không âm | Money | Quy tắc giá trị |
| Tồn kho không âm | Book | Bất biến của một đầu sách |
| Không xuất quá tồn kho | Book | Hành vi trên trạng thái hiện tại |
| ISBN không trùng toàn danh mục | Application + Repository + DB | Cần biết các Book khác |
| Người dùng có quyền đổi giá | Authorization policy | Phụ thuộc actor |
| Kho nào được phép nhập/xuất | Application policy | Phụ thuộc ngữ cảnh và quyền |
| Ghi lịch sử điều chỉnh kho | Application/domain event/audit | Cần phối hợp lưu trữ |
| Chuyển kho giữa hai địa điểm | Application/domain service | Liên quan nhiều aggregate/kho |

Application Service điều phối các bước, nhưng không nên tự thực hiện các phép gán trạng thái. Domain Model sở hữu quy tắc của đối tượng; Repository cung cấp dữ liệu cần thiết để application quyết định.

## 10. Luồng MVC khi đăng ký một đầu sách

~~~mermaid
sequenceDiagram
    actor User as Nhân viên
    participant Browser as Trình duyệt
    participant Controller as BookController
    participant App as RegisterBookService
    participant Repo as BookRepository
    participant Domain as Book
    participant DB as Database

    User->>Browser: Nhập thông tin sách
    Browser->>Controller: POST /books
    Controller->>Controller: Bind và validate Request DTO
    Controller->>App: RegisterBookCommand
    App->>Repo: existsByIsbn
    Repo->>DB: Kiểm tra ISBN
    DB-->>Repo: Chưa tồn tại
    App->>Domain: Book.register
    Domain-->>App: Book hợp lệ
    App->>Repo: save(Book)
    Repo->>DB: INSERT
    DB-->>Repo: Commit
    App-->>Controller: BookId
    Controller-->>Browser: Redirect đến trang chi tiết
~~~

Trách nhiệm của từng tầng:

- Controller nhận request, binding và chọn response.
- Request DTO xác định dữ liệu client được phép gửi.
- Application Service kiểm tra điều kiện cần truy vấn, điều phối và quản lý transaction.
- Domain Model xác thực bất biến và thực hiện hành vi.
- Repository tải/lưu aggregate.
- Persistence adapter ánh xạ Domain Model với ORM Entity.

Không để Controller tự tính giá, tự kiểm tra số lượng tồn kho rồi cập nhật từng cột. Cũng không để Book phụ thuộc vào HttpServletRequest hoặc annotation của Spring MVC.

## 11. Request DTO và validation ở Controller

Request DTO là hợp đồng đầu vào, không phải Entity. Nó chỉ chứa các trường người dùng được phép cung cấp.

~~~java
public record RegisterBookRequest(
    @NotBlank String isbn,
    @NotBlank @Size(max = 250) String title,
    @NotEmpty List<@NotBlank String> authors,
    @NotBlank @Size(max = 180) String publisher,
    @Min(1450) int publicationYear,
    @DecimalMin("0.0") BigDecimal price,
    @NotBlank String currencyCode,
    @PositiveOrZero int initialStock
) {}
~~~

Controller:

~~~java
@Controller
@RequestMapping("/books")
public class BookController {
    private final RegisterBookService registerBook;

    public BookController(RegisterBookService registerBook) {
        this.registerBook = registerBook;
    }

    @PostMapping
    public String register(
            @Valid @ModelAttribute RegisterBookRequest request,
            BindingResult bindingResult,
            RedirectAttributes redirectAttributes) {

        if (bindingResult.hasErrors()) {
            return "books/new";
        }

        BookId id = registerBook.handle(
            new RegisterBookCommand(
                request.isbn(),
                request.title(),
                request.authors(),
                request.publisher(),
                request.publicationYear(),
                request.price(),
                request.currencyCode(),
                request.initialStock()
            )
        );

        redirectAttributes.addFlashAttribute(
            "message",
            "Book registered successfully"
        );

        return "redirect:/books/" + id.value();
    }
}
~~~

Ví dụ giả định Spring MVC đã cấu hình Bean Validation và có template tương ứng. Nếu dùng REST API, Controller có thể nhận @RequestBody và trả ResponseEntity; quy tắc Domain và Application vẫn giữ nguyên.

Validation ở DTO giúp phát hiện lỗi cấu trúc/định dạng sớm. Domain vẫn phải kiểm tra lại các bất biến quan trọng vì use case cũng có thể được gọi từ job, message consumer hoặc test không đi qua Controller.

### 11.1. Không nhận các trường do server quyết định

RegisterBookRequest không chứa:

- BookId do server sinh.
- Status do quy trình đăng ký quyết định.
- CreatedAt hoặc UpdatedAt.
- Version của database.
- Audit actor.
- Các cờ nội bộ.

Không dùng hidden field để truyền dữ liệu được coi là đáng tin cậy. Client có thể sửa mọi giá trị gửi lên.

## 12. Các use case thay đổi Model

### 12.1. Cập nhật metadata

Application tải Book rồi gọi hành vi:

~~~java
public class UpdateBookMetadataService {
    private final BookRepository books;
    private final Clock clock;

    public UpdateBookMetadataService(BookRepository books, Clock clock) {
        this.books = books;
        this.clock = clock;
    }

    public void handle(UpdateBookMetadataCommand command) {
        Book book = books.findById(command.bookId())
            .orElseThrow(BookNotFoundException::new);

        List<AuthorName> authors = command.authors().stream()
            .map(AuthorName::new)
            .toList();

        book.changeMetadata(
            command.title(),
            authors,
            command.publisher(),
            command.publicationYear(),
            Year.now(clock).getValue()
        );

        books.save(book);
    }
}
~~~

Nếu ISBN được coi là định danh thư mục bất biến sau khi đăng ký, không cho phép cập nhật nó qua form chỉnh sửa thông thường. Nếu nghiệp vụ cho phép sửa, cần kiểm tra uniqueness và audit riêng.

### 12.2. Nhập kho

~~~java
public class ReceiveBookStockService {
    private final BookRepository books;

    public ReceiveBookStockService(BookRepository books) {
        this.books = books;
    }

    public void handle(ReceiveBookStockCommand command) {
        Book book = books.findById(command.bookId())
            .orElseThrow(BookNotFoundException::new);

        book.receiveStock(command.quantity());
        books.save(book);
    }
}
~~~

Domain Model kiểm tra quantity dương, trạng thái ACTIVE và overflow. Application Service có thể ghi nhận người thực hiện, mã phiếu nhập và phát audit/domain event.

### 12.3. Xuất kho

~~~java
public class RemoveBookStockService {
    private final BookRepository books;

    public RemoveBookStockService(BookRepository books) {
        this.books = books;
    }

    public void handle(RemoveBookStockCommand command) {
        Book book = books.findById(command.bookId())
            .orElseThrow(BookNotFoundException::new);

        book.removeStock(command.quantity());
        books.save(book);
    }
}
~~~

Nếu xuất kho để hoàn tất đơn bán, use case bán hàng còn cần kiểm tra quyền, đơn hàng và các quy tắc liên quan. Không nên để một endpoint công khai gọi removeStock mà không có ngữ cảnh nghiệp vụ.

### 12.4. Lưu trữ đầu sách

~~~java
public class ArchiveBookService {
    private final BookRepository books;

    public ArchiveBookService(BookRepository books) {
        this.books = books;
    }

    public void handle(BookId id) {
        Book book = books.findById(id)
            .orElseThrow(BookNotFoundException::new);

        book.archive();
        books.save(book);
    }
}
~~~

Lưu trữ giữ lịch sử và các tham chiếu tới đầu sách. Xóa vật lý chỉ nên được cân nhắc khi không còn ràng buộc lịch sử, đơn hàng, báo cáo hoặc yêu cầu lưu trữ dữ liệu.

## 13. Quy tắc nghiệp vụ cần thêm khi hệ thống phát triển

Model ban đầu không nên dự đoán mọi tính năng tương lai. Tuy nhiên, cần biết khi nào một quy tắc mới yêu cầu khái niệm hoặc aggregate mới.

### 13.1. Quản lý từng bản sao vật lý

Nếu mỗi cuốn sách có mã vạch và vị trí riêng, thêm BookCopy:

- Book là thông tin đầu sách.
- BookCopy là một bản vật lý có định danh.
- BookCopy có tình trạng như AVAILABLE, DAMAGED hoặc LOST.
- Stock có thể được suy ra từ các bản sao ở trạng thái phù hợp.

Khi đó, một trường stockQuantity trên Book có thể không đủ để trả lời vị trí hoặc tình trạng của từng bản.

### 13.2. Mượn/trả thư viện

Nếu hệ thống là thư viện, cần thêm:

- Member: người mượn.
- Loan: lượt mượn.
- DueDate: hạn trả.
- LoanStatus: trạng thái lượt mượn.
- Quy tắc số sách được mượn tối đa.
- Quy tắc gia hạn, quá hạn và tiền phạt.

Loan thường là một aggregate riêng vì có vòng đời và quy tắc độc lập. Không nên thêm borrowerId, dueDate, returnedAt vào Book nếu một đầu sách có nhiều bản và nhiều lượt mượn theo thời gian.

### 13.3. Nhiều kho

Nếu có nhiều địa điểm, tồn kho cần gắn với Warehouse hoặc StockItem theo cặp BookId/WarehouseId. Chuyển kho liên quan giảm số lượng ở kho nguồn và tăng ở kho đích; cần transaction hoặc quy trình nhất quán phù hợp.

### 13.4. Lịch sử giá và nhập xuất

Nếu cần truy vết, thêm PriceChange hoặc StockMovement dưới dạng bản ghi lịch sử/audit. Không nên chỉ ghi đè giá hoặc quantity nếu nghiệp vụ yêu cầu biết ai thay đổi, lúc nào và vì lý do gì.

## 14. Persistence Model và mapping

Domain Model không nhất thiết có cùng cấu trúc với bảng. Ví dụ JPA Entity:

~~~java
@Entity
@Table(
    name = "books",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_books_isbn",
        columnNames = "isbn"
    )
)
public class BookJpaEntity {
    @Id
    private UUID id;

    @Column(nullable = false, length = 13)
    private String isbn;

    @Column(nullable = false)
    private String title;

    @ElementCollection
    @CollectionTable(
        name = "book_authors",
        joinColumns = @JoinColumn(name = "book_id")
    )
    @OrderColumn(name = "author_position")
    @Column(name = "author_name", nullable = false)
    private List<String> authors = new ArrayList<>();

    @Column(nullable = false)
    private String publisher;

    private int publicationYear;
    private BigDecimal price;
    private String currencyCode;
    private int stockQuantity;
    private String status;

    @Version
    private long version;

    protected BookJpaEntity() {}
}
~~~

Adapter có thể triển khai Repository port và map dữ liệu. Ví dụ rút gọn:

Trong ví dụ JPA này, danh sách AuthorName được lưu như collection các giá trị trong bảng book_authors. Adapter chuyển mỗi AuthorName thành String khi ghi và tái tạo Value Object khi đọc. Nếu Author là aggregate độc lập, hãy lưu AuthorId tham chiếu thay vì dùng element collection.

~~~java
public interface SpringDataBookRepository
        extends JpaRepository<BookJpaEntity, UUID> {
    boolean existsByIsbn(String isbn);
}
~~~

Port của ứng dụng nhận Isbn13, còn adapter chuyển nó sang chuỗi lưu trong database:

~~~java
@Override
public boolean existsByIsbn(Isbn13 isbn) {
    return data.existsByIsbn(isbn.value());
}
~~~

Unique constraint ở database là lớp bảo vệ cuối cùng cho ISBN. @Version giúp phát hiện cập nhật đồng thời; khi xảy ra optimistic locking conflict, adapter/application cần chuyển lỗi thành kết quả có thể xử lý. Các use case đọc rồi cập nhật như nhập/xuất kho và cập nhật metadata cũng cần transaction phù hợp để thao tác trên aggregate nhất quán.

Khi đọc một bản ghi, adapter dùng factory reconstitute để tái tạo cả trạng thái ACTIVE/ARCHIVED và kiểm tra lại bất biến của aggregate. Khi lưu, adapter phải giữ version persistence đã đọc để optimistic locking phát hiện xung đột; không được tạo một JPA entity mới với version mặc định cho mỗi lần cập nhật.

Không nên để Controller trả BookJpaEntity trực tiếp. Dùng View Model hoặc Response DTO để giữ hợp đồng giao diện độc lập với schema.

## 15. View Model cho danh sách và chi tiết

Màn hình danh sách thường cần dữ liệu khác với aggregate đầy đủ:

~~~java
public record BookListItem(
    UUID id,
    String isbn,
    String title,
    String authorsText,
    String priceText,
    int stockQuantity,
    String statusLabel
) {}
~~~

Màn hình chi tiết có thể cần thêm nhà xuất bản và năm xuất bản:

~~~java
public record BookDetailView(
    UUID id,
    String isbn,
    String title,
    List<String> authors,
    String publisher,
    int publicationYear,
    String formattedPrice,
    int stockQuantity,
    String statusLabel
) {}
~~~

Query service có thể trả projection từ database thay vì tải toàn bộ aggregate cho từng dòng danh sách. Với thao tác ghi, Application vẫn tải Book aggregate qua BookRepository để bảo vệ hành vi.

Một View Model có thể chứa canEditPrice hoặc canArchive để ẩn/hiện nút. Đây chỉ là hỗ trợ trải nghiệm; server vẫn phải kiểm tra quyền khi nhận command.

## 16. Ánh xạ lỗi nghiệp vụ

Khi quy tắc bị vi phạm, application/web adapter cần chuyển kết quả thành phản hồi phù hợp.

| Lỗi | Ví dụ | HTTP thường dùng |
|---|---|---|
| Request không hợp lệ | ISBN thiếu hoặc quantity không phải số | 400 Bad Request |
| Không tìm thấy | BookId không tồn tại | 404 Not Found |
| Trùng dữ liệu | ISBN đã được đăng ký | 409 Conflict |
| Sai trạng thái | Không thể nhập kho khi ARCHIVED | 409 Conflict |
| Không đủ tồn kho | Xuất nhiều hơn số lượng hiện có | 409 Conflict |
| Không có quyền | Nhân viên không được đổi giá | 403 Forbidden |

Với giao diện HTML, có thể trả lại form kèm lỗi field hoặc redirect kèm flash message. Với REST API, trả error code ổn định và nội dung không tiết lộ dữ liệu nội bộ.

Không trả stack trace cho người dùng. Log kỹ thuật và thông báo nghiệp vụ là hai mục đích khác nhau.

## 17. Transaction và cập nhật đồng thời

Hai nhân viên có thể cùng xuất kho từ một đầu sách. Nếu cả hai cùng đọc stockQuantity = 5 và mỗi người xuất 4, một cách triển khai không có kiểm soát đồng thời có thể làm mất cập nhật hoặc tạo số lượng sai.

Các lựa chọn thường gặp:

- Optimistic locking với @Version và retry có giới hạn.
- Pessimistic locking cho thao tác cần khóa hàng trong thời gian ngắn.
- Câu lệnh cập nhật nguyên tử có điều kiện như stock_quantity >= requested_quantity.
- Ghi nhận StockMovement để truy vết từng lần thay đổi.

Transaction giúp một lần cập nhật được commit/rollback nhất quán, nhưng không tự giải quyết mọi race condition. Cần kiểm tra conflict và không retry vô hạn.

Nếu cần audit nhập/xuất, ghi StockMovement cùng transaction với thay đổi tồn kho hoặc dùng outbox khi phát sự kiện ra hệ thống khác. Không coi một dòng log là sổ cái tồn kho.

## 18. Kiểm thử Model và quy tắc nghiệp vụ

Domain Model nên có thể được kiểm thử mà không cần khởi động Spring hoặc database.

### 18.1. Test Value Object

~~~java
@Test
void isbn13RejectsInvalidCheckDigit() {
    assertThrows(
        IllegalArgumentException.class,
        () -> new Isbn13("9780306406158")
    );
}
~~~

Dùng một ISBN mẫu có checksum hợp lệ cho trường hợp thành công và một giá trị sai checksum cho trường hợp bị từ chối.

### 18.2. Test bất biến tồn kho

~~~java
@Test
void cannotRemoveMoreStockThanAvailable() {
    Book book = anActiveBookWithStock(3);

    assertThrows(
        BookRuleViolation.class,
        () -> book.removeStock(4)
    );

    assertEquals(3, book.stockQuantity());
}
~~~

### 18.3. Test nhập kho

~~~java
@Test
void receivingStockIncreasesQuantity() {
    Book book = anActiveBookWithStock(2);

    book.receiveStock(5);

    assertEquals(7, book.stockQuantity());
}
~~~

### 18.4. Test lưu trữ

~~~java
@Test
void cannotArchiveBookWithRemainingStock() {
    Book book = anActiveBookWithStock(1);

    assertThrows(
        BookRuleViolation.class,
        book::archive
    );
}
~~~

### 18.5. Test Application Service

Dùng fake BookRepository để kiểm tra:

- ISBN trùng bị từ chối.
- Book được tạo với trạng thái ACTIVE.
- Clock được dùng để xác định năm hiện tại.
- Repository save chỉ được gọi khi Model hợp lệ.
- Không lưu khi quy tắc Domain từ chối.
- Xử lý unique constraint conflict nếu hai request đăng ký cùng ISBN.

### 18.6. Test MVC và persistence

- MVC test kiểm tra DTO binding, Bean Validation, redirect và lỗi.
- Repository integration test kiểm tra unique ISBN, mapping và optimistic locking.
- End-to-end test kiểm tra luồng đăng ký hoặc nhập/xuất kho qua các tầng.

Không cần database cho test ISBN checksum hoặc số lượng không thể âm. Ngược lại, unit test không chứng minh unique constraint của database hoạt động.

## 19. Những lỗi thiết kế thường gặp

### Tạo Book chỉ để khớp bảng

Một lớp có field và setter không bảo vệ quy tắc. Hãy xác định hành vi như receiveStock, removeStock, archive và changePrice.

### Trộn đầu sách với từng bản sao vật lý

Một đầu sách có thể có nhiều bản. Nếu cần barcode và tình trạng từng cuốn, tạo BookCopy thay vì nhồi tất cả vào Book.

### Cho phép Controller tự sửa status và quantity

Controller chỉ nhận tương tác. Chuyển trạng thái và thay đổi số lượng phải đi qua hành vi Domain.

### Tin ISBN duy nhất chỉ vì đã kiểm tra trước khi lưu

Hai request đồng thời có thể cùng vượt qua existsByIsbn. Database unique constraint vẫn cần thiết.

### Dùng double cho giá

Dùng BigDecimal và quy tắc currency/rounding rõ ràng.

### Bind thẳng JPA Entity vào form

Client có thể gửi trường nội bộ như status, stockQuantity hoặc version. Dùng Request DTO theo allowlist.

### Serialize trực tiếp entity

Có thể lộ trường nội bộ, tạo vòng lặp quan hệ và lazy-loading query. Trả DTO/View Model.

### Đưa quyền người dùng vào Book

Book không cần biết HTTP session hoặc role của Spring Security. Kiểm tra quyền ở application policy; Book bảo vệ bất biến của chính nó.

### Lưu trữ bằng cách xóa vật lý

Xóa có thể làm mất lịch sử và phá tham chiếu. Ưu tiên trạng thái ARCHIVED khi nghiệp vụ cần giữ dữ liệu.

### Gom toàn bộ nghiệp vụ tương lai vào Model ban đầu

Mượn/trả, nhiều kho, từng bản sao và lịch sử giá có thể cần aggregate riêng. Chỉ thêm khái niệm khi yêu cầu xuất hiện và có quy tắc cụ thể.

## 20. Quy trình xác định Model cho một chức năng quản lý sách

Khi nhận yêu cầu mới, hãy làm theo trình tự:

1. **Làm rõ phạm vi.** Quản lý đầu sách, từng bản sao, tồn kho hay mượn/trả?
2. **Xác định tác nhân.** Ai được tạo, sửa, nhập/xuất và lưu trữ?
3. **Liệt kê hành động.** Dùng động từ nghiệp vụ thay vì bắt đầu từ danh sách cột.
4. **Viết bất biến.** Điều kiện nào phải luôn đúng trước và sau hành động?
5. **Chọn Entity và Value Object.** Xác định identity và giá trị có quy tắc.
6. **Xác định aggregate root.** Đối tượng nào sở hữu trạng thái và bảo vệ thay đổi?
7. **Tách quy tắc nhiều đối tượng.** Dùng Repository, Application Service hoặc policy khi cần.
8. **Thiết kế DTO và View Model.** Chỉ nhận/trả dữ liệu theo hợp đồng giao diện.
9. **Đặt persistence constraint.** Unique, version và transaction bảo vệ dữ liệu ở database.
10. **Viết test trước cho bất biến.** Bao phủ cả trường hợp hợp lệ và bị từ chối.

Trước khi hoàn thành, hãy tự hỏi:

- Book đang đại diện đầu sách hay một bản sao vật lý?
- ISBN được chuẩn hóa và kiểm tra ở đâu?
- Quy tắc duy nhất được bảo vệ thế nào khi có request đồng thời?
- Có thể tạo tồn kho âm qua bất kỳ hành vi nào không?
- Đầu sách ARCHIVED còn được nhập hoặc xuất kho không?
- Controller có đang tự gán trạng thái hoặc giá không?
- Client có thể gửi trường do server quyết định không?
- View có đang serialize trực tiếp JPA Entity không?
- Nếu thêm mượn/trả, có cần Loan aggregate riêng không?
- Các bất biến có unit test độc lập với database không?

## 21. Kết luận

Xác định Model cho ứng dụng quản lý sách bắt đầu từ phạm vi và quy tắc nghiệp vụ, không phải từ cấu trúc bảng. Trong ví dụ này, Book là Aggregate Root đại diện một đầu sách và số lượng tồn kho; BookId, Isbn13, AuthorName và Money là các kiểu giá trị có quy tắc riêng. Book bảo vệ trạng thái, giá và tồn kho qua những hành vi có tên nghiệp vụ.

Application Service điều phối use case, kiểm tra ISBN duy nhất qua Repository và quản lý transaction; Controller xử lý HTTP và DTO; persistence adapter lưu aggregate; View Model cung cấp dữ liệu phù hợp cho màn hình. Khi phân biệt rõ những trách nhiệm này, ứng dụng có thể dùng chung quy tắc giữa nhiều giao diện, kiểm thử dễ dàng và mở rộng sang quản lý bản sao, nhiều kho hoặc mượn/trả mà không làm Model ban đầu trở nên mơ hồ.

