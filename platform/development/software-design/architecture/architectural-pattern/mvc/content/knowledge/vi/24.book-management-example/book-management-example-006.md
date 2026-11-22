# Luồng hiển thị danh sách có phân trang và lọc

Trong ứng dụng quản lý sách, trang danh sách thường là nơi người dùng bắt đầu tìm kiếm và chọn một cuốn sách để xem chi tiết. Khi số lượng sách tăng lên, trả toàn bộ bản ghi trong một request sẽ làm chậm truy vấn, tăng bộ nhớ và khiến giao diện khó sử dụng. Phân trang giới hạn số kết quả mỗi lần tải; bộ lọc giúp thu hẹp tập dữ liệu theo từ khóa, thể loại hoặc trạng thái.

Đây là một luồng MVC điển hình: Controller nhận query parameter, chuẩn hóa điều kiện tìm kiếm và gọi use case; Model/query service lấy một trang dữ liệu từ repository; View trình bày danh sách, trạng thái rỗng và các liên kết điều hướng. Các tham số tìm kiếm được đặt trong URL để người dùng có thể tải lại, đánh dấu trang hoặc chia sẻ kết quả.

Bài học xây dựng luồng này bằng Spring MVC và Thymeleaf. Trọng tâm là hợp đồng request/response, phân trang ổn định, lọc an toàn, giữ nguyên điều kiện khi chuyển trang và kiểm thử những trường hợp quan trọng.

## 1. Hành vi mong muốn của trang danh sách sách

Giả sử hệ thống quản lý các trường thông tin:

- Mã sách và tiêu đề.
- Tác giả.
- Thể loại.
- Trạng thái lưu hành, ví dụ đang có, đang mượn hoặc ngừng lưu hành.
- Ngày xuất bản.

Người dùng mở trang danh sách, nhập từ khóa, chọn thể loại hoặc trạng thái, rồi chuyển qua các trang kết quả. Một hợp đồng giao diện hợp lý có thể là:

| Thành phần | Hành vi |
|---|---|
| GET /books | Hiển thị trang đầu tiên với bộ lọc mặc định |
| keyword | Tìm trong tiêu đề hoặc tên tác giả |
| categoryId | Chỉ lấy sách thuộc thể loại được chọn |
| status | Chỉ lấy sách có trạng thái được chọn |
| page | Số trang, bắt đầu từ 0 trong API nội bộ |
| size | Số dòng mỗi trang, có giới hạn tối đa |
| sort | Trường sắp xếp thuộc danh sách cho phép |
| direction | asc hoặc desc |
| Kết quả | Danh sách sách, tổng số kết quả và thông tin điều hướng |

Ví dụ URL:

~~~text
/books?keyword=clean&categoryId=3&status=AVAILABLE&page=0&size=20&sort=title&direction=asc
~~~

GET phù hợp với tìm kiếm và lọc vì thao tác chỉ đọc dữ liệu. URL thể hiện trạng thái tìm kiếm nên có thể bookmark, refresh hoặc chia sẻ. Không đưa thông tin bí mật như access token, mật khẩu hoặc dữ liệu cá nhân nhạy cảm vào query string.

## 2. Luồng request qua MVC

Một request danh sách có thể đi qua các bước:

1. Trình duyệt gửi GET với các query parameter.
2. Spring MVC ánh xạ request đến BookController.
3. Controller đọc và chuẩn hóa bộ lọc, trang, kích thước và kiểu sắp xếp.
4. Application service gọi repository port để tìm dữ liệu.
5. Persistence adapter tạo truy vấn có điều kiện và phân trang tại database.
6. Kết quả trang được chuyển thành dữ liệu trình bày.
7. Controller đưa danh sách, bộ lọc và metadata phân trang vào Model của Spring.
8. Thymeleaf render HTML gồm form, bảng sách, trạng thái rỗng và liên kết trang.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as BookController
    participant S as BookSearchService
    participant R as BookRepository
    participant DB as Database
    participant V as Thymeleaf View
    U->>C: GET /books?keyword=clean&page=0
    C->>C: Chuẩn hóa query parameters
    C->>S: BookSearchCriteria
    S->>R: search(criteria)
    R->>DB: Query + ORDER BY + LIMIT/OFFSET
    DB-->>R: Một trang kết quả và tổng số
    R-->>S: BookPage
    S-->>C: BookPage
    C->>V: Model + books/list
    V-->>U: HTML danh sách và điều hướng
~~~

Controller không nên tải tất cả sách rồi mới lọc trong bộ nhớ. Database cần thực hiện WHERE, ORDER BY và giới hạn số dòng để ứng dụng chỉ nhận dữ liệu cần cho trang hiện tại.

## 3. Thiết kế query parameter và quy tắc mặc định

Một bộ lọc nên có giá trị mặc định rõ ràng và được chuẩn hóa trước khi tạo truy vấn:

| Tham số | Mặc định | Quy tắc |
|---|---|---|
| keyword | null | trim khoảng trắng, chuỗi rỗng thành null, giới hạn độ dài |
| categoryId | null | chỉ nhận ID hợp lệ; kiểm tra quyền/phạm vi nếu cần |
| status | null | chỉ nhận enum đã công bố |
| page | 0 | không cho giá trị âm |
| size | 20 | tối thiểu 1, tối đa 100 hoặc mức phù hợp |
| sort | title | ánh xạ qua allowlist |
| direction | asc | chỉ chấp nhận asc hoặc desc |

Giới hạn kích thước trang giúp tránh một request yêu cầu hàng trăm nghìn bản ghi. Nếu client gửi size=100000, server nên clamp về giới hạn hoặc trả lỗi validation theo hợp đồng. Không dùng nguyên giá trị tùy ý.

Khi người dùng thay đổi bộ lọc, cần quay về trang đầu tiên. Ví dụ đang ở page=4 mà đổi category, kết quả mới có thể chỉ có một trang; giữ page=4 sẽ tạo trang rỗng dù vẫn có sách phù hợp.

Phân biệt số trang nội bộ và số trang hiển thị:

- Spring Data thường dùng page index bắt đầu từ 0.
- Giao diện thường hiển thị trang đầu là 1.
- Khi tạo URL điều hướng, dùng lại index bắt đầu từ 0.
- Khi hiển thị cho người dùng, cộng 1.

## 4. Request model cho bộ lọc

Có thể gom các query parameter thành một form object để binding. Ví dụ đơn giản:

~~~java
public class BookListFilter {
    @Size(max = 100)
    private String keyword;

    @Positive
    private Long categoryId;
    private BookStatus status;

    private Integer page = 0;

    private Integer size = 20;

    private String sort = "title";
    private String direction = "asc";

    // Getters and setters
}
~~~

Đây là request model của web adapter. Nó mô tả những gì người dùng có thể gửi, không phải domain entity Book. Nếu một giá trị không bind được, ví dụ status không thuộc enum, Spring có thể tạo binding error; Controller cần xử lý theo hợp đồng thay vì để exception bất ngờ xuất hiện.

Một lựa chọn khác là khai báo từng tham số bằng @RequestParam. Cách này rõ ràng với endpoint ít trường; form object thuận tiện khi bộ lọc có nhiều trường và cần đưa trạng thái hiện tại trở lại View.

### 4.1. Chuẩn hóa dữ liệu trước khi tìm kiếm

Không nên đưa trực tiếp mọi giá trị từ request vào Pageable hoặc truy vấn. Tạo một đối tượng tiêu chí đã được chuẩn hóa:

~~~java
public enum BookSort {
    TITLE,
    AUTHOR,
    PUBLISHED_AT
}

public enum SortDirection {
    ASC,
    DESC
}

public record BookSearchCriteria(
        String keyword,
        Long categoryId,
        BookStatus status,
        int page,
        int size,
        BookSort sort,
        SortDirection direction
) {
    public static BookSearchCriteria from(BookListFilter filter) {
        String keyword = filter.getKeyword();
        if (keyword != null) {
            keyword = keyword.trim();
            if (keyword.isEmpty()) {
                keyword = null;
            }
        }

        int page = Math.max(0,
                filter.getPage() == null ? 0 : filter.getPage());
        int requestedSize = filter.getSize() == null
                ? 20 : filter.getSize();
        int size = Math.max(1, Math.min(requestedSize, 100));

        BookSort sort = switch (filter.getSort() == null
                ? "" : filter.getSort().toLowerCase(Locale.ROOT)) {
            case "author" -> BookSort.AUTHOR;
            case "publishedat" -> BookSort.PUBLISHED_AT;
            default -> BookSort.TITLE;
        };

        SortDirection direction =
                "desc".equalsIgnoreCase(filter.getDirection())
                        ? SortDirection.DESC
                        : SortDirection.ASC;

        return new BookSearchCriteria(
                keyword,
                filter.getCategoryId(),
                filter.getStatus(),
                page,
                size,
                sort,
                direction
        );
    }
}
~~~

Đoạn mã minh họa chính sách chuẩn hóa. Trong dự án thực tế, cần quyết định rõ có trả lỗi cho tham số sai hay tự dùng giá trị mặc định. Không nên âm thầm cắt hoặc sửa dữ liệu theo cách làm người dùng khó hiểu nếu đó là lỗi cần thông báo.

Nếu dùng Bean Validation, hãy xử lý BindingResult ngay cạnh tham số được validate. Nếu chọn chính sách clamp, kiểm tra null và giới hạn trước khi tạo Pageable để tránh lỗi runtime. Với categoryId, cần xác minh thể loại tồn tại và thuộc phạm vi mà người dùng được phép xem.

Trong ví dụ này, keyword dài hơn 100 ký tự và categoryId không hợp lệ bị Bean Validation từ chối; page âm được đưa về 0 và size được giới hạn trong khoảng 1–100. Controller trả trang báo lỗi khi binding/validation thất bại. Nhờ vậy, quy tắc xử lý sai đầu vào nhất quán với code minh họa.

## 5. Allowlist cho trường sắp xếp

Sắp xếp là một phần của query contract, nhưng tên cột hoặc thuộc tính không thể được bind như một giá trị SQL thông thường. Không nối trực tiếp chuỗi sort do client gửi vào câu SQL.

Ví dụ không an toàn:

~~~java
String sql = "select * from books order by " + requestSort;
~~~

Nếu requestSort được nối thẳng vào SQL, người dùng có thể đưa biểu thức ngoài dự kiến vào câu truy vấn. Ngay cả khi dùng ORM, không nên cho client tùy ý chọn mọi property vì có thể làm lộ trường nội bộ hoặc tạo truy vấn rất tốn kém.

Hãy ánh xạ tên công khai sang thuộc tính được phép:

~~~java
private Sort toSpringSort(BookSearchCriteria criteria) {
    String property = switch (criteria.sort()) {
        case TITLE -> "title";
        case AUTHOR -> "author.name";
        case PUBLISHED_AT -> "publishedAt";
    };

    Sort.Direction direction =
            criteria.direction() == SortDirection.DESC
                    ? Sort.Direction.DESC
                    : Sort.Direction.ASC;

    return Sort.by(direction, property)
            .and(Sort.by(Sort.Direction.ASC, "id"));
}
~~~

Thêm ID làm tiêu chí phụ tạo thứ tự ổn định khi nhiều sách có cùng tiêu đề, tác giả hoặc ngày xuất bản. Nếu không có tie-breaker, các bản ghi cùng giá trị sort có thể đổi vị trí giữa những lần request và xuất hiện trùng hoặc bị bỏ sót khi chuyển trang.

Allowlist cũng giúp API có thể dùng tên thân thiện như publishedAt trong khi entity/database dùng một tên khác. Không trả tên property nội bộ hoặc câu SQL cho client.

## 6. Phân trang ở tầng database

Phân trang nên được thực hiện trong truy vấn. Với Spring Data JPA, Pageable chứa page index, page size và sort; repository có thể trả Page để có danh sách hiện tại cùng tổng số phần tử.

Ví dụ repository:

~~~java
public interface BookJpaRepository
        extends JpaRepository<BookEntity, Long> {

    @Query(
        value = """
            select new com.example.library.book.BookListItem(
                b.id, b.title, a.name, c.name, b.status, b.publishedAt
            )
            from BookEntity b
            join b.author a
            left join b.category c
            where (
                :keyword is null
                or lower(b.title) like lower(concat('%', :keyword, '%'))
                or lower(a.name) like lower(concat('%', :keyword, '%'))
            )
            and (:categoryId is null or c.id = :categoryId)
            and (:status is null or b.status = :status)
            """,
        countQuery = """
            select count(b)
            from BookEntity b
            join b.author a
            left join b.category c
            where (
                :keyword is null
                or lower(b.title) like lower(concat('%', :keyword, '%'))
                or lower(a.name) like lower(concat('%', :keyword, '%'))
            )
            and (:categoryId is null or c.id = :categoryId)
            and (:status is null or b.status = :status)
            """
    )
    Page<BookListItem> search(
            @Param("keyword") String keyword,
            @Param("categoryId") Long categoryId,
            @Param("status") BookStatus status,
            Pageable pageable
    );
}
~~~

BookListItem là projection chỉ chứa dữ liệu cần cho hàng trong danh sách:

~~~java
public record BookListItem(
        Long id,
        String title,
        String authorName,
        String categoryName,
        BookStatus status,
        LocalDate publishedAt
) {
}
~~~

JPQL constructor projection cần constructor/record signature khớp thứ tự và kiểu dữ liệu trong select. Tên package trong ví dụ là minh họa; thay bằng package thực tế. Nếu quan hệ tác giả hoặc thể loại có thể thiếu, hãy điều chỉnh join và kiểu dữ liệu tương ứng.

### 6.1. Vì sao cần count query?

Page thường cần biết tổng số kết quả để tính tổng số trang và hiển thị “đang xem 1–20 trong 235 sách”. Spring Data có thể tạo count query tự động, nhưng với truy vấn có join hoặc projection phức tạp, khai báo countQuery rõ giúp kiểm soát chi phí và tính đúng.

Nếu giao diện chỉ cần nút “Tiếp theo” và không cần tổng số trang, cân nhắc Slice. Slice chỉ cần biết có trang kế tiếp hay không và có thể tránh truy vấn COUNT riêng.

### 6.2. Không tải toàn bộ entity khi chỉ cần danh sách

Trang danh sách thường không cần nội dung mô tả dài, ảnh nhị phân, lịch sử mượn hoặc toàn bộ quan hệ của Book. Projection giảm lượng dữ liệu truyền từ database và tránh tải quan hệ không cần thiết.

Nếu dùng entity và template truy cập author hoặc category lazy, có thể phát sinh N+1 query. Hãy kiểm tra SQL thực tế, dùng projection, fetch join phù hợp hoặc entity graph cho dữ liệu cần thiết.

## 7. Repository port và kết quả phân trang

Trong ứng dụng đơn giản, application service có thể trực tiếp dùng Page của Spring Data. Nếu muốn giữ application layer độc lập Spring, hãy định nghĩa kiểu kết quả trang riêng và để persistence adapter chuyển đổi.

Kiểu kết quả độc lập:

~~~java
public record BookPage(
        List<BookListItem> items,
        int page,
        int size,
        long totalItems,
        int totalPages
) {
    public boolean hasPrevious() {
        return totalPages > 0 && page > 0 && page < totalPages;
    }

    public boolean hasNext() {
        return totalPages > 0 && page < totalPages - 1;
    }
}
~~~

Repository port:

~~~java
public interface BookSearchRepository {
    BookPage search(BookSearchCriteria criteria);
}
~~~

Persistence adapter chuyển tiêu chí sang Pageable và Page:

~~~java
@Repository
public class JpaBookSearchAdapter implements BookSearchRepository {
    private final BookJpaRepository books;

    public JpaBookSearchAdapter(BookJpaRepository books) {
        this.books = books;
    }

    @Override
    public BookPage search(BookSearchCriteria criteria) {
        Pageable pageable = PageRequest.of(
                criteria.page(),
                criteria.size(),
                toSpringSort(criteria)
        );

        Page<BookListItem> result = books.search(
                criteria.keyword(),
                criteria.categoryId(),
                criteria.status(),
                pageable
        );

        return new BookPage(
                result.getContent(),
                result.getNumber(),
                result.getSize(),
                result.getTotalElements(),
                result.getTotalPages()
        );
    }

    private Sort toSpringSort(BookSearchCriteria criteria) {
        String property = switch (criteria.sort()) {
            case TITLE -> "title";
            case AUTHOR -> "author.name";
            case PUBLISHED_AT -> "publishedAt";
        };
        Sort.Direction direction =
                criteria.direction() == SortDirection.DESC
                        ? Sort.Direction.DESC
                        : Sort.Direction.ASC;
        return Sort.by(direction, property)
                .and(Sort.by(Sort.Direction.ASC, "id"));
    }
}
~~~

Application service giữ vai trò điều phối:

~~~java
@Service
public class BookSearchService {
    private final BookSearchRepository repository;

    public BookSearchService(BookSearchRepository repository) {
        this.repository = repository;
    }

    public BookPage search(BookSearchCriteria criteria) {
        return repository.search(criteria);
    }
}
~~~

Đây là cấu trúc có nhiều lớp hơn mức tối thiểu. Với một ứng dụng nhỏ, có thể dùng trực tiếp Spring Data Page trong service. Tách port và BookPage có ích khi muốn kiểm thử application logic độc lập framework hoặc có nhiều adapter persistence.

## 8. Controller điều phối trang danh sách

Controller nhận filter, tạo tiêu chí tìm kiếm, gọi service và chuẩn bị dữ liệu cho View:

~~~java
@Controller
@RequestMapping("/books")
public class BookController {
    private final BookSearchService searchBooks;
    private final CategoryQueryService categories;

    public BookController(
            BookSearchService searchBooks,
            CategoryQueryService categories
    ) {
        this.searchBooks = searchBooks;
        this.categories = categories;
    }

    @GetMapping
    public String list(
            @Valid @ModelAttribute BookListFilter filter,
            BindingResult bindingResult,
            Model model
    ) {
        if (bindingResult.hasErrors()) {
            model.addAttribute("categories", categories.listVisible());
            return "books/invalid-filter";
        }

        BookSearchCriteria criteria = BookSearchCriteria.from(filter);
        BookPage result = searchBooks.search(criteria);

        model.addAttribute("books", result);
        model.addAttribute("filter", BookFilterView.from(criteria));
        model.addAttribute("categories", categories.listVisible());
        model.addAttribute(
                "currentPageNumber",
                result.totalPages() == 0 ? 0 : result.page() + 1
        );
        model.addAttribute(
                "pageOutOfRange",
                result.totalPages() > 0 && result.page() >= result.totalPages()
        );
        model.addAttribute(
                "sort",
                criteria.sort().name().toLowerCase(Locale.ROOT)
        );
        model.addAttribute(
                "direction",
                criteria.direction().name().toLowerCase(Locale.ROOT)
        );

        return "books/list";
    }
}
~~~

ViewModel giữ các giá trị đã chuẩn hóa để form hiển thị đúng trạng thái tìm kiếm:

~~~java
public record BookFilterView(
        String keyword,
        Long categoryId,
        BookStatus status,
        int page,
        int size,
        String sort,
        String direction
) {
    public static BookFilterView from(BookSearchCriteria criteria) {
        return new BookFilterView(
                criteria.keyword(),
                criteria.categoryId(),
                criteria.status(),
                criteria.page(),
                criteria.size(),
                criteria.sort().name().toLowerCase(Locale.ROOT),
                criteria.direction().name().toLowerCase(Locale.ROOT)
        );
    }
}
~~~

Controller trong ví dụ kiểm tra BindingResult trước khi chạy tìm kiếm; View books/invalid-filter trình bày lỗi binding/validation cùng form đã nhập. Nếu category list phụ thuộc tenant hoặc quyền, CategoryQueryService phải trả đúng phạm vi người dùng được phép xem. Không để Controller tự lấy danh sách category bằng truy vấn database.

### 8.1. Khi page vượt quá trang cuối

Nếu người dùng gửi page rất lớn, truy vấn có thể trả danh sách rỗng dù bộ lọc vẫn có kết quả. Có vài chính sách:

- Trả trang rỗng và giữ nguyên page index.
- Chuyển về trang cuối hợp lệ.
- Redirect về trang đầu tiên với thông báo.
- Trả lỗi validation nếu page nằm ngoài giới hạn.

Chọn một chính sách nhất quán. Với trang tìm kiếm thông thường, trả trang rỗng hoặc chuyển về trang cuối thường dễ hiểu; tránh âm thầm hiển thị dữ liệu của trang khác mà URL vẫn ghi page cũ.

Trong ví dụ Controller, pageOutOfRange cho phép View hiển thị thông báo và liên kết quay về trang đầu. Nếu sản phẩm muốn tự chuyển về trang cuối, hãy thực hiện redirect với toàn bộ filter/sort được giữ nguyên và page được thay bằng index hợp lệ.

## 9. View: form lọc, bảng kết quả và điều hướng

View cần trình bày cả dữ liệu hiện tại và trạng thái tìm kiếm. Một form GET cơ bản:

~~~html
<form method="get" action="/books">
  <label for="keyword">Từ khóa</label>
  <input id="keyword" name="keyword" type="search" />

  <label for="categoryId">Thể loại</label>
  <select id="categoryId" name="categoryId">
    <option value="">Tất cả thể loại</option>
    <!-- Các option được render từ danh sách category -->
  </select>

  <label for="status">Trạng thái</label>
  <select id="status" name="status">
    <option value="">Tất cả trạng thái</option>
    <option value="AVAILABLE">Đang có</option>
    <option value="BORROWED">Đang mượn</option>
    <option value="WITHDRAWN">Ngừng lưu hành</option>
  </select>

  <button type="submit">Lọc sách</button>
  <a href="/books">Xóa bộ lọc</a>
</form>
~~~

Đây là cấu trúc HTML minh họa. Trong Thymeleaf, dùng form binding hoặc thuộc tính động để giữ giá trị hiện tại của keyword, category và status sau mỗi lần tải trang. Nút xóa bộ lọc dẫn về URL gốc, đưa page và điều kiện tìm kiếm về mặc định.

### 9.1. Bảng danh sách

Một bảng thường hiển thị:

| Mã | Tiêu đề | Tác giả | Thể loại | Trạng thái | Ngày xuất bản |
|---|---|---|---|---|---|
| BK-001 | Clean Code | Robert C. Martin | Lập trình | Đang có | 2008-08-01 |
| BK-002 | Refactoring | Martin Fowler | Lập trình | Đang mượn | 2018-11-19 |

Các giá trị trên chỉ là dữ liệu minh họa. View nên dùng dữ liệu đã được chuẩn bị trong BookListItem hoặc ViewModel; không gọi repository từ template.

Nếu có thao tác xem chi tiết, liên kết nên dùng ID của sách. Nút sửa/xóa chỉ xuất hiện theo capability hoặc quyền được cung cấp, nhưng endpoint tương ứng vẫn phải kiểm tra authorization ở server.

### 9.2. Thông tin phân trang

Người dùng cần biết:

- Trang hiện tại.
- Số kết quả trong trang.
- Tổng số kết quả nếu hệ thống cung cấp.
- Có trang trước hoặc trang sau hay không.

Ví dụ hiển thị:

~~~text
Đang xem 21–40 trong 235 cuốn sách
Trang 2 / 12
< Trước     1     2     3     ...     12     Sau >
~~~

Nếu tổng số kết quả bằng 0, không hiển thị “Trang 1 / 0”. Hãy hiển thị thông báo không có sách phù hợp và giữ nguyên bộ lọc để người dùng dễ điều chỉnh.

### 9.3. Giữ nguyên bộ lọc khi chuyển trang

Một liên kết phân trang phải giữ keyword, categoryId, status, size, sort và direction. Chỉ page thay đổi.

Ví dụ URL của trang kế tiếp:

~~~text
/books?keyword=clean&categoryId=3&status=AVAILABLE&page=1&size=20&sort=title&direction=asc
~~~

Khi người dùng đổi sort hoặc filter, reset page về 0. Nếu không giữ các điều kiện, người dùng có thể mất ngữ cảnh tìm kiếm khi bấm “Sau”.

Trong Thymeleaf, có thể tạo URL bằng link expression với các query parameter hiện tại. Cần kiểm tra URL được encode đúng, đặc biệt khi keyword có dấu cách, dấu tiếng Việt, ký tự &, dấu + hoặc ký tự đặc biệt.

## 10. Trạng thái rỗng, lỗi và dữ liệu lớn

Trang danh sách cần phân biệt các trạng thái:

| Trạng thái | Nội dung View |
|---|---|
| Có kết quả | Hiển thị bảng và điều hướng |
| Không có sách trong hệ thống | Thông báo chưa có sách, có thể đưa nút thêm sách |
| Không có kết quả phù hợp bộ lọc | Thông báo thử từ khóa hoặc điều kiện khác |
| Tham số không hợp lệ | Thông báo lỗi có thể hiểu và giá trị đã nhập nếu an toàn |
| Lỗi dịch vụ/database | Trang lỗi hoặc response lỗi theo hợp đồng |
| Người dùng không có quyền | 403 hoặc 404 theo chính sách |

Không nên hiển thị cùng một thông báo “Không tìm thấy sách” cho cả hệ thống trống và bộ lọc không khớp nếu người dùng cần hành động khác nhau.

Với tập dữ liệu lớn, tránh hiển thị hàng nghìn số trang. Có thể hiển thị trang trước/sau, một cửa sổ nhỏ quanh trang hiện tại và trang đầu/cuối. Cần đảm bảo nút bị vô hiệu hóa có trạng thái dễ hiểu và có thể truy cập bằng bàn phím.

## 11. Hiệu năng của truy vấn lọc và phân trang

Phân trang giảm lượng dữ liệu truyền về ứng dụng, nhưng không tự động làm mọi truy vấn nhanh. Hiệu năng phụ thuộc bộ lọc, sắp xếp, join, index và số trang.

### 11.1. Index theo điều kiện thường dùng

Nếu người dùng thường lọc theo categoryId và status rồi sắp xếp theo title, cần xem xét query plan và index phù hợp. Index ghép phải dựa trên thứ tự và độ chọn lọc của điều kiện thực tế; không tạo index cho mọi tổ hợp tham số.

Tìm kiếm dạng contains với pattern bắt đầu bằng wildcard như %clean% thường không tận dụng B-tree index thông thường hiệu quả. Với dữ liệu lớn, có thể cân nhắc:

- Prefix search nếu trải nghiệm cho phép.
- Full-text search của database.
- Trigram hoặc index tìm kiếm phù hợp hệ quản trị.
- Search engine riêng khi nhu cầu thực sự cần.

### 11.2. Offset pagination và keyset pagination

PageRequest thường dùng offset/limit. Cách này dễ hiểu và hỗ trợ nhảy đến trang bất kỳ, nhưng truy vấn ở offset rất sâu có thể tốn kém vì database phải đi qua nhiều dòng trước khi trả kết quả.

Keyset pagination (seek pagination) dùng giá trị của bản ghi cuối trang trước làm mốc, ví dụ title và id:

~~~sql
select id, title, author_name
from book_list
where (title, id) > (:lastTitle, :lastId)
order by title asc, id asc
limit :pageSize
~~~

Đây là cú pháp minh họa; hỗ trợ so sánh tuple phụ thuộc database. Có thể thay bằng điều kiện tương đương:

~~~sql
where title > :lastTitle
   or (title = :lastTitle and id > :lastId)
~~~

Keyset pagination phù hợp danh sách rất lớn, cuộn liên tục và không cần nhảy tới trang số bất kỳ. Nó yêu cầu thứ tự ổn định, cursor được mã hóa/kiểm tra phù hợp và cần xác định hành vi khi dữ liệu thay đổi giữa các lần tải.

### 11.3. Tổng số bản ghi và count query

Count query có thể đắt với bộ lọc nhiều join hoặc bảng lớn. Nếu UX không cần tổng số trang, dùng Slice hoặc cursor để chỉ biết còn dữ liệu tiếp theo. Nếu cần tổng số chính xác, hãy đo chi phí count query và tối ưu theo query plan.

Không nên cache tổng số lượng mà không tính đến điều kiện lọc, tenant và thời điểm cập nhật. Cache key phải bao gồm toàn bộ yếu tố làm thay đổi kết quả; authorization vẫn cần được kiểm tra cho từng request.

## 12. Bảo mật trong tìm kiếm và phân trang

Một trang chỉ đọc vẫn có các rủi ro cần kiểm soát:

- **SQL injection:** dùng parameter binding cho keyword, categoryId và status; không nối chuỗi request vào SQL.
- **LIKE wildcard:** nếu muốn tìm chuỗi literal, xử lý/escape ký tự % và _ trong keyword theo cú pháp ESCAPE của database; parameter binding không tự biến wildcard thành ký tự thường.
- **Sort injection:** chỉ cho phép các trường sắp xếp đã định nghĩa.
- **IDOR/tenant leakage:** lọc dữ liệu theo tenant hoặc phạm vi người dùng ở server.
- **Thông tin nhạy cảm:** không đưa token hoặc dữ liệu riêng tư vào URL.
- **Output encoding:** render tiêu đề/tên tác giả như dữ liệu, không diễn giải chúng thành HTML tùy ý.
- **Resource exhaustion:** giới hạn size, độ dài keyword và độ phức tạp truy vấn.
- **Authorization:** kiểm tra quyền xem sách hoặc danh mục ở phía server.

Nếu hệ thống đa tenant, tenantId nên được lấy từ ngữ cảnh đã xác thực và đưa vào tiêu chí truy vấn. Không dùng tenantId tùy ý do client gửi để quyết định phạm vi dữ liệu.

Khi có dữ liệu mà người dùng không được xem, hãy áp dụng policy ở query/service hoặc repository adapter theo thiết kế. Không tải toàn bộ dữ liệu rồi chỉ ẩn một số hàng ở View.

## 13. Kiểm thử luồng danh sách

Kiểm thử cần bao phủ cả bộ lọc, phân trang, sắp xếp và quyền truy cập.

### 13.1. MVC slice test

Ví dụ kiểm tra request GET có filter và page:

~~~java
@WebMvcTest(BookController.class)
class BookControllerTest {
    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    BookSearchService searchBooks;

    @MockitoBean
    CategoryQueryService categories;

    @Test
    void listDisplaysFilteredPage() throws Exception {
        given(searchBooks.search(any()))
                .willReturn(new BookPage(
                        List.of(bookListItem(1L, "Clean Code")),
                        1,
                        20,
                        21,
                        2
                ));
        given(categories.listVisible()).willReturn(List.of());

        mockMvc.perform(get("/books")
                        .param("keyword", "clean")
                        .param("page", "1")
                        .param("size", "20")
                        .param("sort", "title")
                        .param("direction", "asc"))
                .andExpect(status().isOk())
                .andExpect(view().name("books/list"))
                .andExpect(model().attributeExists("books", "filter"))
                .andExpect(model().attribute(
                        "currentPageNumber",
                        2
                ));
    }
}
~~~

Các fixture như bookListItem cần được định nghĩa trong test. Annotation MockitoBean có trong các phiên bản Spring Framework mới; với phiên bản cũ, dùng cơ chế mock bean tương ứng. Nếu Controller yêu cầu principal hoặc bảo mật, cấu hình test authentication đúng theo ứng dụng.

### 13.2. Kiểm thử chuẩn hóa tiêu chí

Unit test cho BookSearchCriteria nên xác nhận:

- Keyword được trim và chuỗi rỗng thành null.
- Page âm trở về 0 hoặc bị từ chối theo chính sách.
- Size vượt giới hạn được clamp hoặc báo lỗi.
- Sort không hợp lệ rơi về mặc định hoặc bị từ chối.
- Direction chỉ nhận asc/desc.
- Bộ lọc category/status được giữ nguyên khi chuyển trang.

### 13.3. Repository integration test

Dùng database test để xác nhận:

- Keyword tìm được tiêu đề và tác giả theo quy tắc.
- Kết hợp category và status bằng AND như hợp đồng.
- Sắp xếp có tie-breaker ID ổn định.
- Trang đầu và trang tiếp theo không trùng bản ghi khi dữ liệu không đổi.
- Count query trả đúng tổng số.
- Không có dữ liệu ngoài tenant/phạm vi được phép.

Không chỉ mock repository rồi kết luận truy vấn JPQL đúng. Query, join, count và sort cần được kiểm thử với database phù hợp.

### 13.4. Kiểm thử giao diện và điều hướng

Browser test có thể xác nhận:

- Form giữ giá trị filter sau khi submit.
- Link trang tiếp theo giữ keyword, category, status và sort.
- Khi đổi filter, page trở về đầu.
- Trạng thái rỗng được hiển thị đúng.
- Nút trước/sau có trạng thái phù hợp.
- Người dùng có thể thao tác bằng bàn phím và label có ý nghĩa.

Không cần snapshot toàn bộ HTML nếu chỉ cần xác nhận các hành vi này. Dùng locator theo role, label và accessible name.

## 14. Ví dụ tổng hợp luồng dữ liệu

Giả sử người dùng tìm sách có từ khóa “clean”, thuộc thể loại lập trình, đang có sẵn, sắp xếp theo tiêu đề tăng dần và xem trang thứ hai.

Request:

~~~text
GET /books?keyword=clean&categoryId=3&status=AVAILABLE&page=1&size=20&sort=title&direction=asc
~~~

Controller chuyển request thành criteria đã chuẩn hóa:

~~~text
keyword = "clean"
categoryId = 3
status = AVAILABLE
page = 1
size = 20
sort = TITLE
direction = ASC
~~~

Repository thực hiện điều kiện lọc, sắp xếp ổn định và lấy 20 dòng:

~~~sql
select ...
from books
where title or author matches 'clean'
  and category_id = 3
  and status = 'AVAILABLE'
order by title asc, id asc
limit 20 offset 20
~~~

View nhận:

- Danh sách 20 sách của trang hiện tại.
- Tổng số kết quả và tổng số trang.
- Bộ lọc đang áp dụng.
- Sort và direction hiện tại.
- Cờ hasPrevious và hasNext.

Khi người dùng bấm trang tiếp theo, URL mới thay page thành 2 và giữ nguyên các điều kiện khác. Khi đổi category, page quay về 0.

## 15. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Tải toàn bộ sách rồi lọc trong Java | Tốn bộ nhớ và thời gian | Lọc/phân trang tại database |
| Không giới hạn page size | Request có thể yêu cầu lượng dữ liệu rất lớn | Clamp hoặc validate size |
| Sort theo chuỗi client gửi trực tiếp | Rủi ro injection và truy vấn ngoài dự kiến | Allowlist trường sort |
| Không có tie-breaker | Thứ tự không ổn định giữa các trang | Thêm ID hoặc khóa duy nhất |
| Đổi filter nhưng giữ page cũ | Kết quả có thể rỗng ngoài ý muốn | Reset page về 0 |
| Link phân trang làm mất filter | Người dùng mất ngữ cảnh tìm kiếm | Giữ tất cả query parameter |
| Template truy cập lazy relation | N+1 query | Projection hoặc fetch dữ liệu có kiểm soát |
| Dùng Page cho UX không cần tổng số | Count query tốn kém | Cân nhắc Slice/cursor |
| Không xử lý page vượt phạm vi | Trang rỗng khó hiểu | Chọn chính sách nhất quán |
| Dùng entity JPA làm ViewModel | Lộ field nội bộ, lazy loading, coupling | Dùng projection/DTO phù hợp |
| Chỉ ẩn hàng ở View | Có thể rò dữ liệu qua request khác | Lọc quyền ở server |
| Cache không đủ filter/tenant | Trả nhầm kết quả | Cache key chứa đủ ngữ cảnh và kiểm tra quyền |

## 16. Checklist review trang danh sách

Trước khi hoàn thiện trang danh sách có lọc và phân trang, hãy kiểm tra:

- URL GET thể hiện trạng thái filter và có thể bookmark không?
- Giá trị mặc định của page, size, sort và direction đã rõ chưa?
- Keyword đã được trim và giới hạn độ dài chưa?
- Page size có giới hạn tối đa không?
- Trường sort có allowlist và tie-breaker ổn định không?
- Filter có được thực hiện tại database không?
- Projection chỉ lấy các trường cần cho danh sách không?
- Count query có thực sự cần thiết không?
- Link trước/sau có giữ mọi filter và sort không?
- Khi thay filter, page có reset về 0 không?
- Trang rỗng, filter không khớp và lỗi tham số có thông báo phù hợp không?
- Query có áp dụng tenant và authorization ở server không?
- Dữ liệu người dùng được escape khi render không?
- Có kiểm thử Controller, criteria, repository và điều hướng không?
- Đã đo query plan và kiểm tra N+1 với dữ liệu đủ lớn chưa?

## 17. Kết luận

Trang danh sách có phân trang và lọc là một ví dụ rõ ràng về cách MVC phối hợp trong ứng dụng quản lý sách. Controller nhận query parameter và điều phối use case; Model/query service chuẩn hóa tiêu chí, truy vấn repository và trả một trang kết quả; View trình bày danh sách, filter hiện tại và điều hướng.

Một luồng tốt thực hiện lọc và phân trang ở database, giới hạn kích thước request, dùng allowlist cho sort, giữ thứ tự ổn định và bảo toàn điều kiện tìm kiếm trong URL. Khi kết hợp kiểm tra quyền, trạng thái rỗng, xử lý lỗi và kiểm thử ở đúng ranh giới, trang danh sách vẫn dễ sử dụng và có thể mở rộng khi số lượng sách tăng lên.
