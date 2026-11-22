# Phân trang, lọc và sắp xếp tại đúng lớp

Trong module **MODEL_VIEW_CONTROLLER**, danh sách dữ liệu thường xuất hiện ở nhiều màn hình: bảng sách, lịch sử giao dịch, danh sách đơn hàng hoặc báo cáo. Khi số bản ghi tăng lên, việc tải toàn bộ dữ liệu về trình duyệt rồi lọc và chia trang ở đó làm tăng thời gian phản hồi, băng thông và bộ nhớ. Nếu Controller tự xử lý từng bản ghi, tự sắp xếp hoặc tự chia trang sau khi tải dữ liệu, trách nhiệm giữa các tầng cũng bị trộn lẫn.

Bài học thuộc chương **Hiệu năng**. Trọng tâm là đặt **phân trang, lọc và sắp xếp tại đúng lớp** trong luồng MVC: View gửi tiêu chí; Controller binding và kiểm tra hợp đồng; application service chuẩn hóa truy vấn và áp dụng phạm vi quyền; repository/query layer chuyển tiêu chí thành truy vấn; database thực hiện lọc, sắp xếp và giới hạn kết quả. Bài học cũng so sánh offset pagination với keyset pagination, hướng dẫn xây dựng API an toàn và chỉ ra các điểm ảnh hưởng trực tiếp đến hiệu năng.

## 1. Vì sao phải đặt đúng lớp?

Giả sử hệ thống quản lý thư viện có 500.000 cuốn sách. Người dùng mở trang danh sách và muốn xem 25 cuốn thuộc danh mục “Lập trình”, sắp xếp theo ngày phát hành mới nhất.

Một cách làm không phù hợp là:

1. Controller tải toàn bộ 500.000 bản ghi.
2. Chuyển toàn bộ entity thành object để hiển thị.
3. Lọc danh mục trong Java.
4. Sắp xếp danh sách trong bộ nhớ.
5. Lấy 25 phần tử tương ứng với trang hiện tại.
6. Trả kết quả cho View.

Cách này khiến ứng dụng đọc và chuyển đổi nhiều dữ liệu mà người dùng không cần. Nó còn có thể tải quan hệ ORM ngoài ý muốn, tạo N+1 query và tiêu tốn bộ nhớ server.

Cách phù hợp hơn là gửi tiêu chí đến tầng truy vấn và để database thực hiện thao tác gần nơi dữ liệu đang được lưu:

~~~sql
SELECT id, title, author_name, published_at
FROM books
WHERE category = :category
ORDER BY published_at DESC, id ASC
LIMIT :page_size
OFFSET :offset;
~~~

Database chỉ trả về phần kết quả cần thiết. Controller không cần biết câu SQL; View không cần nhận hàng trăm nghìn bản ghi để tự cắt danh sách.

### 1.1. Phân công trách nhiệm trong MVC

| Lớp | Trách nhiệm | Không nên làm |
|---|---|---|
| View | Thu thập tiêu chí, hiển thị bộ lọc, liên kết trang và thứ tự sắp xếp | Tải toàn bộ dữ liệu lớn rồi tự lọc/sắp xếp |
| Controller | Binding query parameter, validation, chuyển đổi sang query object, chọn response/view | Viết SQL hoặc chứa thuật toán phân trang dữ liệu |
| Application Service | Áp dụng quyền, tenant scope, giá trị mặc định, giới hạn và điều phối use case truy vấn | Phụ thuộc chi tiết HTML hoặc tự duyệt toàn bộ dữ liệu |
| Repository / Query Adapter | Xây dựng truy vấn có tham số, projection và pagination | Nhận trực tiếp tên cột hoặc đoạn SQL tùy ý từ client |
| Database | Lọc, sắp xếp, giới hạn kết quả, thực hiện count khi cần | Không có trách nhiệm trình bày nhãn hoặc nút trên UI |

Ranh giới cụ thể có thể thay đổi theo quy mô ứng dụng. Một ứng dụng nhỏ có thể để service gọi Spring Data repository trực tiếp; một ứng dụng lớn có thể có query service và query adapter riêng. Điều cần giữ là mỗi lớp chỉ làm phần việc phù hợp với nó.

## 2. Luồng truy vấn danh sách

Một request danh sách thường mang các tham số như keyword, category, status, page, size, sort và direction. Controller chuyển chúng thành một query object rõ nghĩa rồi gọi application service.

~~~mermaid
sequenceDiagram
    autonumber
    actor User as Người dùng
    participant View as View
    participant C as MVC Controller
    participant App as Application Service
    participant Repo as Query Repository
    participant DB as Database

    User->>View: Chọn bộ lọc, trang và thứ tự
    View->>C: GET /books?category=...&page=...&size=...&sort=...
    C->>C: Binding và validation tham số
    C->>App: SearchBooksQuery
    App->>App: Áp dụng quyền, tenant và giới hạn
    App->>Repo: Tìm kiếm theo tiêu chí
    Repo->>DB: WHERE + ORDER BY + LIMIT/OFFSET
    DB-->>Repo: Chỉ phần kết quả được yêu cầu
    Repo-->>App: Page/Slice kết quả
    App-->>C: Kết quả use case
    C-->>View: ViewModel hoặc response DTO
    View-->>User: Danh sách và điều hướng
~~~

Nguyên tắc quan trọng: **lọc và sắp xếp phải được áp dụng trước khi database giới hạn trang**. Nếu lấy trang trước rồi mới lọc, kết quả có thể thiếu phần tử, tổng số trang sai và các trang không phản ánh cùng một tập dữ liệu.

### 2.1. Một query object đại diện cho ý định đọc

Không nên truyền rời rạc nhiều tham số qua mọi lớp nếu chúng cùng mô tả một yêu cầu tìm kiếm. Có thể tạo query object:

~~~java
public record SearchBooksQuery(
    String keyword,
    String category,
    BookStatus status,
    int page,
    int size,
    BookSortField sortBy,
    SortDirection direction
) {}

public enum BookSortField {
    TITLE,
    AUTHOR,
    PUBLISHED_AT
}

public enum SortDirection {
    ASC,
    DESC
}
~~~

Query object ghi nhận hợp đồng truy vấn ở tầng ứng dụng. Nó không cần chứa tên HTML input hay chi tiết URL. Controller chuyển giao thức HTTP sang kiểu này; application service áp dụng quy tắc rồi gọi query repository.

### 2.2. Giá trị mặc định và giới hạn

Một request có thể thiếu page, size hoặc sort. Server nên có giá trị mặc định nhất quán và giới hạn kích thước trang tối đa.

Ví dụ:

- Trang mặc định: trang đầu.
- Kích thước mặc định: 20 bản ghi.
- Kích thước tối đa: 100 bản ghi.
- Sắp xếp mặc định: ngày tạo giảm dần, sau đó ID tăng dần.
- Keyword được trim và giới hạn độ dài.
- Bộ lọc status chỉ nhận giá trị enum được hỗ trợ.

Không nên cho client yêu cầu size bằng 100.000 chỉ vì API chấp nhận một số nguyên. Giới hạn page size là một phần bảo vệ tài nguyên và cần được áp dụng ở server.

## 3. Phân trang là gì?

Pagination chia một tập kết quả thành những phần nhỏ để người dùng duyệt từng phần. Thay vì trả toàn bộ dữ liệu, server trả một trang hoặc một đoạn kết quả cùng thông tin điều hướng cần thiết.

Một response dạng page có thể chứa:

~~~json
{
  "items": [
    {
      "id": "book-101",
      "title": "Thiết kế hệ thống"
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 137,
  "totalPages": 7,
  "hasNext": true,
  "hasPrevious": false
}
~~~

Đây là response minh họa. API cần công bố rõ page là zero-based hay one-based, totalElements có được tính chính xác hay không và dữ liệu có thể thay đổi giữa các request như thế nào.

### 3.1. Phân trang theo số trang (offset pagination)

Offset pagination thường dùng số trang và kích thước trang. Với chỉ số trang bắt đầu từ 0:

\[
\text{offset} = \text{page} \times \text{size}
\]

Nếu giao diện hiển thị trang bắt đầu từ 1:

\[
\text{offset} = (\text{pageNumber} - 1) \times \text{pageSize}
\]

Ví dụ, page = 3 và size = 20 với chỉ số zero-based thì database bỏ qua 60 bản ghi đầu và trả tối đa 20 bản ghi tiếp theo.

~~~sql
SELECT id, title, published_at
FROM books
WHERE category = :category
ORDER BY published_at DESC, id ASC
LIMIT :size OFFSET :offset;
~~~

Ưu điểm:

- Dễ hiểu và dễ triển khai.
- Người dùng có thể nhảy trực tiếp đến một số trang.
- Hợp với màn hình quản trị cần tổng số trang và điều hướng đầu/cuối.
- Được hỗ trợ bởi hầu hết hệ quản trị cơ sở dữ liệu và framework.

Hạn chế:

- Offset càng lớn, database có thể phải đọc và bỏ qua nhiều dòng trước khi trả kết quả.
- Dữ liệu được thêm hoặc xóa giữa các request có thể làm bản ghi dịch chuyển giữa các trang.
- Count query để tính tổng số bản ghi có thể tốn kém với tập dữ liệu lớn.
- Trang sâu có thể chậm dù mỗi trang chỉ trả một số ít bản ghi.

Offset pagination phù hợp với danh sách có quy mô vừa, nhu cầu nhảy trang và thứ tự dữ liệu ít biến động. Với bảng rất lớn hoặc luồng “xem thêm” liên tục, cần cân nhắc keyset pagination.

### 3.2. Phân trang theo cursor (keyset pagination)

Keyset pagination dùng giá trị của bản ghi cuối cùng ở trang trước làm mốc để lấy phần tiếp theo. Thay vì yêu cầu database bỏ qua hàng nghìn dòng, truy vấn yêu cầu các dòng nằm sau mốc sắp xếp.

Giả sử sắp xếp theo ngày phát hành giảm dần và ID tăng dần. Cursor lưu cặp giá trị của phần tử cuối cùng, ví dụ publishedAt và id.

~~~sql
SELECT id, title, published_at
FROM books
WHERE category = :category
  AND (
      published_at < :last_published_at
      OR (
          published_at = :last_published_at
          AND id > :last_id
      )
  )
ORDER BY published_at DESC, id ASC
LIMIT :size;
~~~

Điều kiện so sánh phải khớp chính xác với thứ tự sort. Khi sort có nhiều cột, có null hoặc trộn ASC/DESC, biểu thức cursor cần được thiết kế tương ứng; không thể dùng một phép so sánh đơn giản cho mọi trường hợp.

Ưu điểm:

- Tránh chi phí bỏ qua lượng lớn dòng ở trang sâu.
- Thường ổn định hơn khi có bản ghi mới được thêm vào phía trước.
- Phù hợp nút “Tải thêm”, feed và luồng dữ liệu liên tục.
- Có thể tận dụng index theo các cột sắp xếp.

Hạn chế:

- Khó nhảy thẳng đến trang số 50.
- Cần cursor và quy tắc thứ tự ổn định.
- Tính tổng số trang không tự nhiên như offset.
- Cần xử lý cẩn thận khi giá trị sort thay đổi hoặc có null.

### 3.3. Cursor phải có thứ tự duy nhất

Nếu chỉ sắp xếp theo publishedAt, nhiều sách có thể cùng thời điểm phát hành. Database không bảo đảm thứ tự ổn định giữa các bản ghi có cùng giá trị sort. Vì vậy, cần thêm khóa phụ duy nhất như id:

~~~sql
ORDER BY published_at DESC, id ASC
~~~

ID tạo thứ tự xác định khi published_at bằng nhau. Quy tắc phụ này cũng phải được phản ánh trong điều kiện cursor.

Nếu sort key có thể null, hãy xác định rõ nulls first hoặc nulls last và đưa chính sách đó vào cursor predicate. Cách đơn giản hơn là chọn cột sort không null hoặc chuẩn hóa giá trị sort.

### 3.4. Chọn offset hay keyset?

| Nhu cầu | Offset | Keyset |
|---|---|---|
| Nhảy trực tiếp đến trang bất kỳ | Phù hợp | Không thuận tiện |
| Nút “Tải thêm” | Có thể dùng | Rất phù hợp |
| Trang sâu trên bảng lớn | Có thể chậm | Thường hiệu quả hơn |
| Hiển thị tổng số trang | Thuận tiện nếu có count | Thường không cần hoặc phải tính riêng |
| Dữ liệu liên tục được thêm mới | Có thể bị dịch trang | Ổn định hơn với cursor cố định |
| Triển khai đơn giản | Dễ hơn | Phức tạp hơn |
| Thứ tự sort tùy chọn rộng | Dễ quản lý hơn | Cần xây dựng cursor theo từng thứ tự |

Không có phương pháp nào phù hợp cho mọi màn hình. Chọn theo quy mô dữ liệu, cách người dùng điều hướng, tần suất cập nhật và yêu cầu tổng số.

## 4. Lọc dữ liệu phải thực hiện trước khi phân trang

Filtering chọn ra tập con phù hợp với điều kiện. Các điều kiện thường gặp:

- Từ khóa trong tiêu đề hoặc tên tác giả.
- Danh mục, trạng thái hoặc loại tài nguyên.
- Khoảng ngày tạo hoặc ngày phát hành.
- Khoảng giá hoặc số lượng.
- Chủ sở hữu hoặc tenant hiện tại.
- Kết hợp nhiều điều kiện.

Luồng truy vấn đúng về mặt logic:

~~~mermaid
flowchart TD
    A["Nhận tiêu chí truy vấn"] --> B["Xác thực và chuẩn hóa"]
    B --> C["Thêm điều kiện quyền và tenant"]
    C --> D["Database lọc bằng WHERE"]
    D --> E["Sắp xếp bằng ORDER BY"]
    E --> F["Giới hạn trang hoặc cursor"]
    F --> G["Chọn projection cần thiết"]
    G --> H["Trả kết quả cho View"]
~~~

Database có thể chọn kế hoạch thực thi nội bộ khác nhau, nhưng hợp đồng truy vấn phải bảo đảm các điều kiện lọc áp dụng cho toàn tập dữ liệu trước khi giới hạn phần kết quả.

### 4.1. Không lọc sau khi lấy trang

Giả sử database có 1.000 sách. Server lấy 20 sách đầu tiên rồi mới lọc category = PROGRAMMING trong Java. Nếu trong 20 sách đó chỉ có 3 sách thuộc danh mục, server trả 3 phần tử dù vẫn còn nhiều sách lập trình ở các trang tiếp theo.

Kết quả này sai về mặt phân trang: trang không được lấp đầy dù còn dữ liệu phù hợp, totalElements không đúng và người dùng có thể bỏ lỡ bản ghi. Hãy đưa điều kiện category vào truy vấn trước khi áp dụng limit/offset.

### 4.2. Kết hợp nhiều bộ lọc

Khi người dùng chọn danh mục, trạng thái và khoảng ngày, query repository nên kết hợp các predicate:

~~~sql
SELECT id, title, status, created_at
FROM books
WHERE tenant_id = :tenant_id
  AND category = :category
  AND status = :status
  AND created_at >= :from_date
  AND created_at < :to_date_exclusive
ORDER BY created_at DESC, id ASC
LIMIT :size OFFSET :offset;
~~~

Trong ví dụ, tenant_id được lấy từ ngữ cảnh xác thực phía server. Không dùng giá trị tenant do client tự gửi làm căn cứ phân quyền.

Với khoảng thời gian, điều kiện kết thúc dạng nhỏ hơn mốc ngày tiếp theo (to_date_exclusive) thường giúp biểu diễn một ngày đầy đủ rõ ràng hơn so với cộng một thời điểm cuối ngày có độ chính xác phụ thuộc database.

### 4.3. Tìm kiếm chuỗi và wildcard

Tìm kiếm chứa từ khóa thường dùng LIKE hoặc full-text search. Cần phân biệt người dùng nhập ký tự thường với ký tự wildcard như % và _. Nếu hợp đồng muốn tìm chuỗi nguyên văn, cần escape wildcard và dùng tham số truy vấn.

Không ghép trực tiếp chuỗi client vào SQL. Prepared statement hoặc query parameter giúp tránh SQL injection cho giá trị. Tuy nhiên, tên cột và biểu thức sort không thể được bảo vệ chỉ bằng parameter binding; chúng cần allowlist riêng.

~~~java
String escapeLike(String value) {
    return value
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_");
}
~~~

Khi dùng hàm escape, câu truy vấn phải khai báo ký tự escape tương ứng. Cần kiểm thử với dấu gạch chéo ngược, phần trăm và gạch dưới để tránh kết quả tìm kiếm bất ngờ.

### 4.4. Chuẩn hóa và giới hạn bộ lọc

Application service hoặc lớp chuyển đổi query có thể:

- Trim khoảng trắng đầu/cuối của keyword.
- Chuẩn hóa mã danh mục theo enum.
- Kiểm tra fromDate không sau toDate.
- Giới hạn độ dài keyword.
- Giới hạn số lượng giá trị trong filter dạng danh sách.
- Áp dụng giá trị mặc định cho filter không được cung cấp.
- Bỏ qua filter rỗng theo hợp đồng đã công bố.

Không nên chấp nhận hàng nghìn giá trị trong query parameter mà không giới hạn. Một request có danh sách ID quá lớn có thể tạo câu SQL rất nặng hoặc vượt giới hạn tham số của database.

## 5. Sắp xếp an toàn và ổn định

Sorting xác định thứ tự bản ghi trong tập kết quả đã lọc. Người dùng thường chọn sắp xếp theo tên, ngày tạo, giá hoặc trạng thái.

~~~sql
SELECT id, title, published_at
FROM books
WHERE category = :category
ORDER BY published_at DESC, id ASC
LIMIT :size OFFSET :offset;
~~~

Sắp xếp cần được thực hiện ở database khi dữ liệu lớn. Nếu tải một trang rồi mới sort trong Java, thứ tự chỉ đúng trong 20 bản ghi đã tải, không phải toàn bộ tập kết quả.

### 5.1. Không đưa tên cột tùy ý từ client vào SQL

Một request có thể gửi sortBy = title và direction = asc. Không được ghép nguyên giá trị client vào câu SQL:

~~~java
String sql = "SELECT * FROM books ORDER BY " + request.sortBy();
~~~

Cách này có thể mở ra SQL injection hoặc cho phép truy vấn cột nội bộ không được công khai. Parameter binding không áp dụng cho tên cột hay từ khóa ORDER BY.

Thay vào đó, dùng enum hoặc allowlist:

~~~java
public enum BookSortField {
    TITLE,
    AUTHOR,
    PUBLISHED_AT
}

public enum SortDirection {
    ASC,
    DESC
}
~~~

Ánh xạ enum sang thuộc tính persistence:

~~~java
private static final Map<BookSortField, String> SORT_COLUMNS = Map.of(
    BookSortField.TITLE, "title",
    BookSortField.AUTHOR, "authorName",
    BookSortField.PUBLISHED_AT, "publishedAt"
);

Sort toSort(BookSortField field, SortDirection direction) {
    String property = SORT_COLUMNS.get(field);

    Sort.Direction sortDirection =
        direction == SortDirection.ASC
            ? Sort.Direction.ASC
            : Sort.Direction.DESC;

    return Sort.by(sortDirection, property)
        .and(Sort.by(Sort.Direction.ASC, "id"));
}
~~~

Nếu sortBy không hợp lệ, API có thể trả 400 hoặc dùng sort mặc định theo hợp đồng. Không âm thầm chuyển sang một cột nội bộ bất kỳ. Allowlist cần được cập nhật có chủ đích khi sản phẩm thêm lựa chọn sắp xếp.

### 5.2. Thêm tie-breaker duy nhất

Sắp xếp theo một cột không duy nhất có thể khiến các bản ghi cùng giá trị đổi thứ tự giữa các request. Hãy thêm khóa duy nhất làm tie-breaker, ví dụ id.

~~~sql
ORDER BY title ASC, id ASC
~~~

Thứ tự ổn định đặc biệt quan trọng với pagination. Nếu không có tie-breaker, một bản ghi có thể lặp ở trang trước hoặc biến mất khỏi trang tiếp theo ngay cả khi dữ liệu không thay đổi.

### 5.3. Quy định null và collation

Cần xác định cách sort với giá trị null, chữ hoa/chữ thường, dấu tiếng Việt và collation của database. Ví dụ, sort tên theo collation không phân biệt dấu có thể khác sort theo mã Unicode.

Không giả định thứ tự của database luôn giống thứ tự JavaScript. Nếu server sort, server phải là nguồn quyết định thứ tự; View chỉ hiển thị thứ tự nhận được.

## 6. Ví dụ tổ chức trong Spring MVC

Một Controller nên tập trung vào binding, validation và điều phối. Ví dụ request dùng query parameter:

~~~java
public record BookListRequest(
    String keyword,
    String category,
    BookStatus status,
    @Min(1) Integer page,
    @Min(1) @Max(100) Integer size,
    BookSortField sortBy,
    SortDirection direction
) {}
~~~

Controller chuyển request thành query object:

~~~java
@Controller
@RequestMapping("/books")
public class BookController {
    private final BookQueryService books;

    public BookController(BookQueryService books) {
        this.books = books;
    }

    @GetMapping
    public String list(
        @Valid @ModelAttribute BookListRequest request,
        BindingResult errors,
        Model model
    ) {
        if (errors.hasErrors()) {
            return "books/invalid-query";
        }

        var query = new SearchBooksQuery(
            request.keyword(),
            request.category(),
            request.status(),
            request.page() == null ? 1 : request.page(),
            request.size() == null ? 20 : request.size(),
            request.sortBy() == null
                ? BookSortField.PUBLISHED_AT
                : request.sortBy(),
            request.direction() == null
                ? SortDirection.DESC
                : request.direction()
        );

        var result = books.search(query);
        model.addAttribute("result", result);
        model.addAttribute("filters", request);
        return "books/list";
    }
}
~~~

Trong Spring MVC, BindingResult phải đứng ngay sau tham số được validate. Ví dụ dùng page one-based cho giao diện; khi chuyển sang PageRequest của Spring Data cần đổi thành zero-based. Có thể đặt logic chuyển đổi và default vào một mapper hoặc factory để Controller gọn hơn.

### 6.1. Application service chuẩn hóa và áp dụng quyền

~~~java
@Service
public class BookQueryService {
    private final BookSearchRepository repository;
    private final CurrentUser currentUser;

    public BookQueryService(
        BookSearchRepository repository,
        CurrentUser currentUser
    ) {
        this.repository = repository;
        this.currentUser = currentUser;
    }

    public Page<BookSummary> search(SearchBooksQuery query) {
        int page = Math.max(query.page() - 1, 0);
        int size = Math.min(Math.max(query.size(), 1), 100);

        var criteria = new BookSearchCriteria(
            normalizeKeyword(query.keyword()),
            query.category(),
            query.status(),
            currentUser.tenantId()
        );

        return repository.search(criteria, page, size, query.sortBy(), query.direction());
    }

    private String normalizeKeyword(String keyword) {
        if (keyword == null || keyword.isBlank()) {
            return null;
        }
        return keyword.trim();
    }
}
~~~

Đây là ví dụ minh họa. Với API public, request validation nên từ chối page/size sai theo hợp đồng thay vì âm thầm sửa mọi giá trị; clamp ở service là lớp bảo vệ bổ sung. Tenant ID được lấy từ danh tính đã xác thực, không lấy từ query parameter do client kiểm soát.

### 6.2. Query repository nhận tiêu chí và pageable

Có thể định nghĩa repository theo ý định truy vấn:

~~~java
public interface BookSearchRepository {
    Page<BookSummary> search(
        BookSearchCriteria criteria,
        int page,
        int size,
        BookSortField sortBy,
        SortDirection direction
    );
}
~~~

Adapter triển khai có thể dùng Spring Data JPA Specification, Criteria API, query DSL hoặc SQL có tham số. Trách nhiệm của adapter là chuyển tiêu chí thành điều kiện database và chỉ chọn dữ liệu cần thiết.

Ví dụ một repository Spring Data đơn giản:

~~~java
public interface BookJpaRepository
        extends JpaRepository<BookEntity, UUID>,
                JpaSpecificationExecutor<BookEntity> {
}
~~~

Application service có thể tạo Specification từ những filter được cung cấp rồi gọi findAll(specification, pageable). Với màn hình danh sách cần ít trường, nên cân nhắc projection thay vì tải toàn bộ entity.

### 6.3. Tạo Pageable với sort allowlist

~~~java
Pageable toPageable(
    int zeroBasedPage,
    int size,
    BookSortField sortBy,
    SortDirection direction
) {
    String property = SORT_COLUMNS.get(sortBy);

    Sort.Direction springDirection =
        direction == SortDirection.ASC
            ? Sort.Direction.ASC
            : Sort.Direction.DESC;

    Sort sort = Sort.by(springDirection, property)
        .and(Sort.by(Sort.Direction.ASC, "id"));

    return PageRequest.of(zeroBasedPage, size, sort);
}
~~~

Ví dụ giả định sortBy đã được validate và có trong allowlist. Không truyền trực tiếp chuỗi sort từ client vào PageRequest. Với Spring Data, sort property được framework kiểm tra theo mapping nhưng allowlist vẫn cần thiết để giới hạn các trường API được phép công khai và tránh truy vấn tốn kém ngoài ý muốn.

## 7. Page, Slice và projection

Framework có thể trả kết quả cùng metadata. Chọn kiểu response theo nhu cầu giao diện.

| Kiểu kết quả | Thông tin | Chi phí thường gặp | Phù hợp |
|---|---|---|---|
| List | Chỉ danh sách | Không tự có count/page metadata | Tập nhỏ, đã giới hạn |
| Slice | Nội dung và có trang tiếp theo hay không | Có thể chỉ cần đọc thêm một dòng | “Tải thêm”, cuộn vô hạn |
| Page | Nội dung, số phần tử và tổng số trang | Thường cần count query | Bảng có số trang/tổng số |
| Cursor page | Nội dung và cursor tiếp theo | Không cần offset sâu | Feed hoặc dữ liệu lớn |

### 7.1. Page có thể phát sinh count query

Một Page thường cần biết tổng số phần tử để tính totalPages. Vì vậy, repository có thể chạy một truy vấn lấy dữ liệu và một truy vấn count.

~~~sql
SELECT id, title
FROM books
WHERE category = :category
ORDER BY title ASC, id ASC
LIMIT :size OFFSET :offset;

SELECT COUNT(*)
FROM books
WHERE category = :category;
~~~

Với bộ lọc phức tạp hoặc bảng rất lớn, count query có thể tốn thời gian đáng kể. Nếu UI chỉ cần biết có trang tiếp theo hay không, Slice có thể phù hợp hơn; repository chỉ cần lấy thêm một bản ghi để xác định hasNext.

### 7.2. Projection giảm lượng dữ liệu

Nếu bảng chỉ hiển thị id, title, author và ngày phát hành, không cần tải toàn bộ entity cùng các quan hệ không dùng. Projection giúp giảm dữ liệu đọc, chuyển đổi và serialization.

~~~java
public record BookSummary(
    UUID id,
    String title,
    String authorName,
    LocalDate publishedAt
) {}
~~~

Có thể dùng JPQL constructor projection, interface projection hoặc query DTO. Nếu mapper truy cập quan hệ lazy trên từng entity, ứng dụng có thể tạo N+1 query; projection giúp chọn trường cần thiết ngay trong query.

### 7.3. Tránh fetch join collection với pagination một cách tùy tiện

Fetch join một collection có thể nhân số dòng SQL của mỗi entity cha. Kết hợp với pagination có thể làm database giới hạn trên các dòng join thay vì số entity mong muốn; một số ORM có thể phải tải nhiều dữ liệu rồi phân trang trong memory hoặc phát cảnh báo.

Với danh sách, ưu tiên projection hoặc fetch quan hệ to-one cần thiết. Nếu cần dữ liệu collection, có thể lấy trang ID trước rồi truy vấn phần dữ liệu liên quan theo batch, hoặc dùng chiến lược batch fetching có kiểm soát.

## 8. Index và tối ưu truy vấn

Đặt pagination/filter/sort ở database chỉ hiệu quả khi truy vấn có thể tận dụng index và chọn ít dữ liệu cần thiết. Index phải dựa trên các mẫu truy vấn thực tế, không tạo tùy ý cho mọi cột.

### 8.1. Index theo điều kiện và thứ tự

Giả sử truy vấn phổ biến:

~~~sql
WHERE tenant_id = ?
  AND category = ?
ORDER BY published_at DESC, id ASC
LIMIT 20
~~~

Một index ghép có thể được cân nhắc theo mẫu này, ví dụ:

~~~sql
CREATE INDEX idx_books_tenant_category_published
ON books (tenant_id, category, published_at DESC, id ASC);
~~~

Đây là ví dụ minh họa cho một hệ quản trị hỗ trợ cú pháp index tương ứng. Khả năng sử dụng index còn phụ thuộc database, phân bố dữ liệu, điều kiện truy vấn, collation và kế hoạch thực thi. Cần kiểm tra bằng EXPLAIN/EXPLAIN ANALYZE trên dữ liệu gần thực tế.

### 8.2. Thứ tự cột trong composite index

Index ghép thường cần cân nhắc:

- Các điều kiện equality phổ biến như tenant_id và category.
- Điều kiện range như created_at.
- Cột phục vụ ORDER BY.
- Tính chọn lọc của điều kiện và các query pattern thường dùng.

Không có công thức “cột lọc luôn đứng trước cột sort” áp dụng cho mọi trường hợp. Hãy xem query plan và workload. Một index quá rộng làm tăng chi phí ghi, dung lượng và bảo trì.

### 8.3. Tìm kiếm chứa chuỗi có thể không dùng B-tree hiệu quả

Điều kiện LIKE '%keyword%' thường khó tận dụng B-tree index thông thường vì wildcard ở đầu chuỗi. Với nhu cầu tìm kiếm chứa từ, có thể cân nhắc full-text index, trigram index hoặc search engine chuyên dụng tùy database và ngôn ngữ.

Nếu nghiệp vụ chỉ cần tìm theo tiền tố, điều kiện LIKE 'keyword%' thường thân thiện với B-tree hơn, tùy collation và cách chuẩn hóa dữ liệu.

### 8.4. Chỉ lấy cột cần thiết

Tránh SELECT * cho màn hình danh sách nếu entity có nhiều cột lớn như nội dung văn bản, JSON hoặc blob. Projection giảm I/O, memory và thời gian serialization.

Tương tự, không trả hàng trăm trường trong response chỉ vì entity có chúng. Hợp đồng ViewModel/response nên phản ánh đúng thông tin màn hình cần.

## 9. Tính nhất quán khi dữ liệu thay đổi giữa các trang

Offset pagination có thể gặp hiện tượng dịch chuyển dữ liệu. Ví dụ, người dùng đang xem trang 2. Trước khi họ mở trang 3, một bản ghi mới được thêm lên đầu danh sách. Các phần tử sau đó dịch vị trí; người dùng có thể thấy một phần tử lặp hoặc bỏ sót.

Keyset pagination giảm hiện tượng dịch chuyển do thêm mới trước cursor, nhưng không giải quyết mọi thay đổi. Nếu bản ghi thay đổi sort key hoặc bị xóa, kết quả tiếp theo vẫn có thể khác.

Các lựa chọn:

- Dùng keyset cho luồng duyệt liên tục trên tập dữ liệu thay đổi thường xuyên.
- Dùng snapshot hoặc transaction phù hợp khi cần một tập kết quả nhất quán trong một phiên đọc.
- Ghi nhận thời điểm snapshot hoặc version nếu sản phẩm cần duyệt một kết quả cố định.
- Chấp nhận dữ liệu mới nhất ở mỗi request nếu đó là trải nghiệm mong muốn và mô tả rõ.
- Dùng sort key ổn định và tie-breaker duy nhất.

Không nên giữ một transaction database mở trong nhiều phút chỉ để người dùng chuyển trang. Snapshot dài có thể gây áp lực lên database. Hãy chọn mức nhất quán theo yêu cầu nghiệp vụ.

## 10. URL và trải nghiệm phân trang

Với danh sách có thể bookmark hoặc chia sẻ, tiêu chí lọc, trang và sort thường nên nằm trong query string:

~~~text
/books?keyword=java&category=programming&page=2&size=25&sortBy=PUBLISHED_AT&direction=DESC
~~~

Ưu điểm:

- Reload vẫn giữ được bộ lọc.
- Nút Back/Forward khôi phục trạng thái điều hướng.
- Người dùng có thể bookmark hoặc chia sẻ liên kết.
- Server-rendered MVC có thể dựng lại trang từ query string.
- Hỗ trợ kiểm thử và tái hiện lỗi dễ hơn.

Không đưa thông tin bí mật hoặc dữ liệu cá nhân nhạy cảm vào URL. Cũng cần giới hạn độ dài query string và số lượng filter.

### 10.1. Giữ filter khi chuyển trang

Khi người dùng chọn trang tiếp theo, các filter và sort hiện tại cần được giữ lại. Nếu chỉ đổi page mà bỏ category và keyword, danh sách có thể nhảy sang tập dữ liệu khác.

Ví dụ với Thymeleaf, các placeholder dưới đây đại diện cho biến template được chuẩn bị từ ViewModel:

~~~html
<a th:href="@{/books(page=NEXT_PAGE, size=PAGE_SIZE, keyword=KEYWORD, category=CATEGORY)}">Tiếp theo</a>
~~~

Template thực tế cần xử lý khi hasNext là false, giữ trạng thái filter rỗng hợp lý và tạo liên kết trước/sau phù hợp.

### 10.2. Reset trang khi filter thay đổi

Nếu người dùng đang ở trang 8 rồi thay category, kết quả mới có thể chỉ có 2 trang. Khi filter thay đổi, UI nên đưa page về trang đầu. Nếu không, server có thể trả trang rỗng dù tập kết quả mới có dữ liệu.

Tương tự, thay đổi sort có thể khiến bản ghi chuyển vị trí. Đặt lại cursor hoặc page khi tiêu chí truy vấn thay đổi.

### 10.3. Accessibility

- Dùng nav có nhãn, ví dụ “Điều hướng trang kết quả”.
- Đánh dấu trang hiện tại bằng aria-current="page".
- Nút trước/sau có tên dễ hiểu và trạng thái disabled khi không dùng được.
- Hiển thị tổng số hoặc phạm vi kết quả nếu API cung cấp.
- Không chỉ dùng màu sắc để chỉ trang hiện tại.
- Sau khi đổi trang bằng client-side navigation, cập nhật tiêu đề hoặc vùng thông báo phù hợp để người dùng trình đọc màn hình biết nội dung đã thay đổi.

## 11. Bảo mật và giới hạn truy vấn

Filter và sort cũng là bề mặt bảo mật. Một endpoint danh sách cần áp dụng quyền trước khi trả kết quả.

### 11.1. Tenant và quyền truy cập phải do server quyết định

Không tin tenantId, ownerId hoặc role do client gửi. Application service lấy phạm vi truy cập từ người dùng đã xác thực và thêm predicate vào truy vấn.

Ví dụ:

~~~sql
SELECT id, title
FROM books
WHERE tenant_id = :current_tenant
  AND category = :category
ORDER BY title ASC, id ASC
LIMIT :size OFFSET :offset;
~~~

Nếu endpoint hỗ trợ admin xem tenant khác, quyền đó cần được kiểm tra riêng và có audit. Không để filter tenant tùy ý trở thành cơ chế vượt quyền.

### 11.2. Sort và filter cần allowlist

Chỉ công khai những trường sort và filter mà sản phẩm cho phép. Không cho client truy vấn cột nội bộ, dữ liệu nhạy cảm hoặc quan hệ tốn kém.

Dùng enum/allowlist cho:

- Tên trường sort.
- Hướng sort ASC/DESC.
- Các filter enum.
- Các toán tử như equals, contains, before, after.
- Các field có thể tìm kiếm.

Giá trị filter dùng query parameter binding; identifier/cột sort được ánh xạ từ danh sách cho phép.

### 11.3. Giới hạn chi phí request

Một endpoint có thể bị lạm dụng bằng cách yêu cầu size quá lớn, keyword cực dài, nhiều filter hoặc sort trên cột không có index. Cần:

- Page size tối đa.
- Giới hạn chiều dài keyword.
- Giới hạn số giá trị trong filter dạng danh sách.
- Timeout truy vấn hợp lý.
- Rate limit theo user/tenant khi cần.
- Chỉ cho phép sort/filter trên trường đã được đánh giá.
- Giám sát query chậm và số lượng bản ghi trả về.

## 12. Cache kết quả danh sách

Danh sách có thể được cache nếu dữ liệu phù hợp và có chiến lược invalidation rõ ràng. Cache key cần bao gồm mọi yếu tố ảnh hưởng đến kết quả:

- Tenant hoặc phạm vi quyền.
- Keyword và filter.
- Page/size hoặc cursor.
- Sort field và direction.
- Locale nếu nội dung được dịch.
- Phiên bản dữ liệu hoặc chính sách cache.

Không dùng chung cache key giữa hai tenant nếu kết quả có thể khác nhau theo quyền. Không cache response riêng tư vào public cache. Với dữ liệu thay đổi thường xuyên, TTL ngắn hoặc invalidation theo event có thể phù hợp hơn.

Cache không sửa được một truy vấn sai hoặc thiếu index. Trước tiên cần bảo đảm query đúng và đo hiệu năng; sau đó mới cân nhắc cache.

## 13. Những lỗi thiết kế thường gặp

| Dấu hiệu | Hệ quả | Cách cải thiện |
|---|---|---|
| Tải toàn bộ dữ liệu rồi chia trang trong Controller | Tốn bộ nhớ và thời gian | Đưa limit/offset hoặc cursor vào query |
| Lọc sau khi lấy trang | Thiếu kết quả và sai total count | Áp dụng WHERE trước pagination |
| Sort trong View sau khi nhận một trang | Chỉ sort đúng phần tử của trang đó | Sắp xếp toàn tập kết quả ở query layer |
| Dùng sortBy trực tiếp để ghép SQL | Có nguy cơ injection và lộ cột nội bộ | Dùng enum/allowlist |
| Không có tie-breaker | Thứ tự không ổn định giữa các trang | Thêm khóa duy nhất vào ORDER BY |
| Page size không giới hạn | Request có thể tạo tải lớn | Đặt default và maximum |
| Count query luôn chạy dù UI không cần tổng số | Tăng chi phí database | Dùng Slice hoặc cursor khi phù hợp |
| Offset rất sâu trên bảng lớn | Database phải bỏ qua nhiều dòng | Cân nhắc keyset pagination |
| Fetch join collection với pagination | Nhân dòng, phân trang sai hoặc tải quá nhiều | Projection, batch hoặc truy vấn hai bước |
| Không giữ filter trong URL/link | Chuyển trang làm mất tiêu chí | Giữ query string và reset page khi filter đổi |
| Không lấy tenant từ server context | Có thể lộ dữ liệu tenant khác | Thêm phạm vi quyền ở query service |
| Tạo index theo cảm tính | Tốn dung lượng và chi phí ghi mà không cải thiện query | Đo bằng execution plan |
| Cache key bỏ qua filter hoặc tenant | Trả kết quả sai hoặc lộ dữ liệu | Bao gồm mọi yếu tố ảnh hưởng quyền và kết quả |
| Không kiểm thử dữ liệu thay đổi đồng thời | Lặp hoặc bỏ sót bản ghi | Xác định consistency model và test cursor/offset |

## 14. Kiểm thử phân trang, lọc và sắp xếp

Kiểm thử không chỉ xác nhận response có 20 phần tử. Cần xác nhận tập dữ liệu, thứ tự, metadata và giới hạn quyền.

### 14.1. Kiểm thử phân trang

- Trang đầu có đúng số phần tử tối đa.
- Trang cuối trả số phần tử còn lại.
- Page vượt phạm vi trả kết quả rỗng hoặc lỗi theo hợp đồng.
- Size bằng 0, âm hoặc vượt giới hạn bị xử lý đúng.
- Page index one-based/zero-based được chuyển đổi nhất quán.
- Các trang không lặp bản ghi trong dữ liệu tĩnh.
- Tie-breaker tạo thứ tự ổn định khi nhiều bản ghi cùng sort key.

### 14.2. Kiểm thử filter

- Mỗi filter đơn lẻ hoạt động đúng.
- Kết hợp nhiều filter dùng AND/OR theo hợp đồng.
- Filter rỗng được bỏ qua hoặc xử lý theo chính sách.
- Khoảng ngày xử lý đúng biên đầu và cuối.
- Keyword có ký tự %, _, dấu tiếng Việt và ký tự đặc biệt.
- Filter không hợp lệ trả lỗi rõ ràng.
- Tenant scope luôn được áp dụng.

### 14.3. Kiểm thử sort

- Mỗi sort field được allowlist hoạt động đúng.
- ASC và DESC tạo thứ tự tương ứng.
- Cùng giá trị sort key vẫn có thứ tự ổn định nhờ tie-breaker.
- Sort field không hỗ trợ bị từ chối hoặc dùng default theo hợp đồng.
- Client không thể truy vấn cột nội bộ hoặc đưa biểu thức SQL vào sort.

### 14.4. Kiểm thử hiệu năng và tích hợp

- Kiểm tra số query phát sinh và phát hiện N+1.
- Kiểm tra execution plan trên dữ liệu đủ lớn.
- Đo thời gian count query riêng với data query.
- So sánh offset sâu với keyset nếu đó là use case.
- Kiểm tra response chỉ chứa projection cần thiết.
- Kiểm tra cache key không trộn tenant/filter.
- Kiểm tra hành vi khi dữ liệu được thêm/xóa giữa các lần chuyển trang.

Không nên đặt ngưỡng mili giây tùy ý mà không xét môi trường và kích thước dữ liệu. Hãy đo bằng dữ liệu gần thực tế, theo dõi percentile và kiểm tra query plan thay vì chỉ dựa vào một lần chạy trên máy phát triển.

## 15. Checklist đặt phân trang, lọc và sắp xếp đúng lớp

- [ ] View chỉ gửi tiêu chí và hiển thị kết quả.
- [ ] Controller binding, validation và chuyển đổi HTTP request.
- [ ] Application service áp dụng default, maximum, tenant và authorization.
- [ ] Query repository thực hiện filter, sort và pagination trong database.
- [ ] Filter được áp dụng trước khi giới hạn trang.
- [ ] Sort field và direction được allowlist.
- [ ] Thứ tự có tie-breaker duy nhất.
- [ ] Chọn offset hay keyset theo cách người dùng điều hướng và quy mô dữ liệu.
- [ ] Chỉ tính total count khi giao diện thực sự cần.
- [ ] Dùng projection để tránh tải entity/quan hệ không cần thiết.
- [ ] Kiểm tra index và execution plan theo query pattern thực tế.
- [ ] URL giữ filter/sort/page nếu cần bookmark và Back/Forward.
- [ ] Đổi filter hoặc sort thì reset page/cursor phù hợp.
- [ ] Cache key bao gồm phạm vi quyền và mọi tiêu chí ảnh hưởng kết quả.
- [ ] Có kiểm thử cho dữ liệu biên, quyền truy cập, sort, cursor và dữ liệu thay đổi đồng thời.

Phân trang, lọc và sắp xếp là một phần của hợp đồng truy vấn xuyên suốt MVC. View diễn đạt điều người dùng muốn xem; Controller chuyển request thành dữ liệu có cấu trúc; application service kiểm soát phạm vi và giới hạn; repository tạo truy vấn an toàn; database thực hiện công việc trên tập dữ liệu đầy đủ. Khi đặt đúng trách nhiệm, ứng dụng tránh tải dữ liệu thừa, giữ kết quả nhất quán và mở rộng tốt hơn khi danh sách tăng lên.
