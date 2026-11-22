# Query và pagination trong Spring for GraphQL

GraphQL không quy định sẵn một cơ chế phân trang. API cần thiết kế argument và kiểu trả về để client có thể lấy dữ liệu theo từng phần, biết còn dữ liệu hay không và tiếp tục từ vị trí trước đó. Trong Spring for GraphQL, `@QueryMapping` nhận các argument qua `@Argument`, sau đó resolver chuyển chúng đến service hoặc repository để thực hiện truy vấn có giới hạn.

Hai chiến lược thường gặp là **offset pagination** (phân trang theo số trang và kích thước) và **cursor pagination** (phân trang theo con trỏ). Offset dễ triển khai và phù hợp với giao diện có số trang. Cursor phù hợp với danh sách lớn, dữ liệu thường xuyên thay đổi hoặc thao tác tải tiếp liên tục. Chọn chiến lược theo cách client sử dụng dữ liệu và đặc điểm truy vấn của hệ thống.

## 1. Vì sao query cần pagination?

Một query trả về toàn bộ dữ liệu có thể đơn giản lúc đầu:

~~~graphql
type Query {
    books: [Book!]!
}
~~~

Khi số lượng sách tăng lên hàng trăm nghìn, client tải toàn bộ danh sách sẽ gây ra một số vấn đề:

- Response lớn làm tăng băng thông và thời gian truyền dữ liệu.
- Server phải đọc, chuyển đổi và serialize nhiều bản ghi dù client chỉ hiển thị một phần.
- Resolver có thể tạo áp lực lớn lên database và bộ nhớ.
- Giao diện khó triển khai tải thêm, cuộn vô hạn hoặc chuyển trang.

Pagination giới hạn số phần tử trả về trong một lần thực thi. Client có thể lấy trang đầu, sau đó gửi request tiếp theo dựa trên page number hoặc cursor.

Pagination cũng cần được kết hợp với giới hạn query depth, query complexity, filter và authorization. Giới hạn `first` hoặc `size` chỉ kiểm soát số phần tử của một field; nó không tự giới hạn tổng chi phí của toàn bộ GraphQL operation.

## 2. Thiết kế offset pagination bằng SDL

Offset pagination thường dùng hai argument:

- `page`: số trang, thường bắt đầu từ `0`.
- `size`: số phần tử tối đa trong một trang.

Có thể thêm `sort` để client chọn một số thứ tự sắp xếp được server cho phép.

~~~graphql
enum BookSort {
    TITLE_ASC
    TITLE_DESC
    CREATED_AT_DESC
}

type Query {
    books(
        page: Int! = 0
        size: Int! = 20
        sort: BookSort! = CREATED_AT_DESC
    ): BookPage!
}

type BookPage {
    content: [Book!]!
    page: Int!
    size: Int!
    totalElements: Int!
    totalPages: Int!
    hasNext: Boolean!
}

type Book {
    id: ID!
    title: String!
    createdAt: String!
}
~~~

`BookPage` là kiểu wrapper do API định nghĩa. GraphQL client có thể chọn cả dữ liệu sách lẫn metadata phân trang. Không nên trả thẳng `Page<Book>` như một hợp đồng API và kỳ vọng GraphQL tự suy ra schema; hãy ánh xạ kết quả Spring Data sang một DTO hoặc record có các field được khai báo rõ ràng.

Các argument `page`, `size` và `sort` có default value nên client được phép bỏ qua chúng. Nếu bỏ qua, GraphQL sử dụng các giá trị `0`, `20` và `CREATED_AT_DESC`. Nếu client truyền `null` cho argument Non-Null, request không hợp lệ.

`totalElements` trong ví dụ dùng GraphQL `Int`, là số nguyên có dấu 32-bit. Nếu hệ thống có thể vượt giới hạn này, không nên ép `long` sang `int`; hãy dùng custom scalar số nguyên lớn hoặc thiết kế metadata khác phù hợp với hợp đồng API.

## 3. Triển khai offset pagination bằng Spring Data

Spring for GraphQL không tự quyết định cách truy vấn database cho mọi API. Resolver nhận argument, tạo `Pageable` và gọi service. Spring Data có thể dùng `Pageable` để tạo truy vấn có `LIMIT` và `OFFSET` cho repository hỗ trợ pagination.

### 3.1. Định nghĩa model và kiểu trả về

Ví dụ dùng Java record cho dữ liệu API:

~~~java
public record Book(
        String id,
        String title,
        String createdAt
) {}
~~~

~~~java
import java.util.List;

public record BookPage(
        List<Book> content,
        int page,
        int size,
        int totalElements,
        int totalPages,
        boolean hasNext
) {}
~~~

Enum Java tương ứng với SDL:

~~~java
public enum BookSort {
    TITLE_ASC,
    TITLE_DESC,
    CREATED_AT_DESC
}
~~~

Trong ví dụ SDL phía trên, `createdAt` được khai báo là `String`. Ứng dụng thực tế nên cân nhắc custom scalar `DateTime` để thể hiện rõ định dạng thời gian; ở đây `String` chỉ giúp tập trung vào luồng phân trang.

### 3.2. Service nhận Pageable

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public interface BookService {
    Page<Book> findAll(Pageable pageable);
}
~~~

Service triển khai bằng repository Spring Data tương ứng:

~~~java
public class JpaBookService implements BookService {

    private final BookRepository bookRepository;

    public JpaBookService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @Override
    public Page<Book> findAll(Pageable pageable) {
        return bookRepository.findAll(pageable)
                .map(entity -> new Book(
                        entity.getId().toString(),
                        entity.getTitle(),
                        entity.getCreatedAt().toString()
                ));
    }
}
~~~

`BookRepository` có thể khai báo như sau nếu dùng Spring Data JPA:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository extends JpaRepository<BookEntity, Long> {}
~~~

`BookEntity` là entity persistence của ứng dụng. Việc chuyển entity sang DTO giúp GraphQL API không phụ thuộc trực tiếp vào cấu trúc persistence.

### 3.3. Resolver dùng @QueryMapping và @Argument

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookQueryController {

    private static final int MAX_PAGE_SIZE = 100;

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public BookPage books(
            @Argument("page") int page,
            @Argument("size") int size,
            @Argument("sort") BookSort sort
    ) {
        if (page < 0) {
            throw new IllegalArgumentException("page must be zero or greater");
        }
        if (size < 1 || size > MAX_PAGE_SIZE) {
            throw new IllegalArgumentException(
                    "size must be between 1 and " + MAX_PAGE_SIZE
            );
        }

        Pageable pageable = PageRequest.of(page, size, toSort(sort));
        Page<Book> result = bookService.findAll(pageable);

        return new BookPage(
                result.getContent(),
                result.getNumber(),
                result.getSize(),
                Math.toIntExact(result.getTotalElements()),
                result.getTotalPages(),
                result.hasNext()
        );
    }

    private Sort toSort(BookSort sort) {
        return switch (sort) {
            case TITLE_ASC -> Sort.by(Sort.Direction.ASC, "title")
                    .and(Sort.by(Sort.Direction.ASC, "id"));
            case TITLE_DESC -> Sort.by(Sort.Direction.DESC, "title")
                    .and(Sort.by(Sort.Direction.ASC, "id"));
            case CREATED_AT_DESC -> Sort.by(Sort.Direction.DESC, "createdAt")
                    .and(Sort.by(Sort.Direction.DESC, "id"));
        };
    }
}
~~~

Các điểm quan trọng:

- `@QueryMapping` ánh xạ method vào field `Query.books`.
- `@Argument` bind argument GraphQL vào tham số Java theo tên được chỉ định.
- `PageRequest.of(page, size, sort)` tạo yêu cầu phân trang cho Spring Data.
- `MAX_PAGE_SIZE` giới hạn lượng dữ liệu client có thể yêu cầu trong một lần.
- `toSort` dùng enum allowlist để client chỉ chọn được các thứ tự sắp xếp đã định nghĩa.
- Thêm `id` làm tiêu chí phụ cho thứ tự `createdAt` để kết quả có thứ tự ổn định khi nhiều bản ghi cùng thời điểm.

`Math.toIntExact` sẽ ném lỗi nếu tổng số phần tử vượt giới hạn của Java `int`. Ví dụ minh họa dùng `Int` trong SDL nên cần bảo đảm dữ liệu nằm trong giới hạn; với hệ thống lớn, hãy đổi hợp đồng sang scalar phù hợp thay vì âm thầm cắt cụt số liệu.

## 4. Gọi query phân trang từ client

Client có thể gửi query với variables:

~~~graphql
query Books($page: Int!, $size: Int!, $sort: BookSort!) {
    books(page: $page, size: $size, sort: $sort) {
        content {
            id
            title
        }
        page
        size
        totalElements
        totalPages
        hasNext
    }
}
~~~

Variables cho trang đầu:

~~~json
{
    "page": 0,
    "size": 20,
    "sort": "CREATED_AT_DESC"
}
~~~

Variables cho trang tiếp theo:

~~~json
{
    "page": 1,
    "size": 20,
    "sort": "CREATED_AT_DESC"
}
~~~

Client có thể sử dụng `hasNext` để quyết định có hiển thị nút “Tải thêm” hay không. `totalPages` và `totalElements` phù hợp với giao diện hiển thị số trang hoặc tổng số kết quả.

Nếu schema đã khai báo default value, client có thể gọi ngắn hơn:

~~~graphql
query {
    books {
        content {
            id
            title
        }
        hasNext
    }
}
~~~

## 5. Page, Slice và giới hạn truy vấn đếm

Spring Data cung cấp một số abstraction khác nhau cho pagination:

| Kiểu | Dữ liệu cung cấp | Chi phí thường gặp |
| --- | --- | --- |
| `Page<T>` | Content, page metadata và tổng số phần tử/trang | Thường cần thêm truy vấn `COUNT` để tính tổng |
| `Slice<T>` | Content và thông tin có trang tiếp theo hay không | Có thể tránh truy vấn tổng số phần tử; thường đọc thêm một phần tử để xác định `hasNext` |
| `Window<T>` | Một cửa sổ kết quả theo cơ chế scrolling của Spring Data | Có thể hỗ trợ offset hoặc keyset scrolling tùy repository và phiên bản |

Nếu giao diện chỉ cần nút “Tải thêm”, `Slice<T>` có thể đủ và tránh chi phí đếm toàn bộ bản ghi. Nếu cần tổng số trang, `Page<T>` thuận tiện hơn nhưng truy vấn count có thể tốn kém với điều kiện filter phức tạp hoặc bảng lớn.

Không nên đưa nguyên abstraction persistence vào GraphQL schema. Hãy chuyển nó thành DTO có field phù hợp với client, ví dụ `BookSlice { content, hasNext }` hoặc `BookPage { content, totalElements, totalPages }`.

## 6. Hạn chế của offset pagination

Offset pagination dễ hiểu, nhưng có một số giới hạn:

**Trang sâu có thể chậm.** Truy vấn `OFFSET 500000 LIMIT 20` có thể khiến database phải đi qua nhiều dòng trước khi trả về 20 dòng cần thiết, tùy execution plan và index.

**Dữ liệu thay đổi có thể làm lệch trang.** Nếu một bản ghi mới được thêm vào đầu danh sách sau khi client tải trang 0, request trang 1 có thể lặp lại một phần tử đã thấy hoặc bỏ qua phần tử khác. Xóa bản ghi cũng có thể làm vị trí các phần tử dịch chuyển.

**Thứ tự phải xác định.** Nếu chỉ sắp xếp theo một cột có giá trị trùng, bản ghi có thể đổi thứ tự giữa các request. Hãy thêm một khóa duy nhất làm tiêu chí phụ, ví dụ `createdAt DESC, id DESC`.

Offset phù hợp khi dữ liệu không thay đổi quá thường xuyên, số trang không quá sâu và giao diện cần nhảy trực tiếp đến trang bất kỳ. Với danh sách lớn hoặc cập nhật liên tục, cursor/keyset pagination thường phù hợp hơn.

## 7. Thiết kế cursor pagination bằng GraphQL connection

Cursor pagination dùng một giá trị con trỏ đại diện cho vị trí cuối cùng đã đọc. Request tiếp theo gửi cursor đó để lấy các phần tử đứng sau nó theo thứ tự đã định nghĩa.

Một schema connection theo quy ước phổ biến:

~~~graphql
type Query {
    books(first: Int! = 20, after: String): BookConnection!
}

type BookConnection {
    edges: [BookEdge!]!
    pageInfo: PageInfo!
    totalCount: Int
}

type BookEdge {
    cursor: String!
    node: Book!
}

type PageInfo {
    hasNextPage: Boolean!
    hasPreviousPage: Boolean!
    startCursor: String
    endCursor: String
}

type Book {
    id: ID!
    title: String!
    createdAt: String!
}
~~~

Các thành phần:

- `first`: số phần tử tối đa muốn lấy.
- `after`: cursor của edge cuối cùng client đã nhận.
- `edges`: danh sách các cạnh, mỗi cạnh chứa cursor và node.
- `pageInfo`: metadata để client biết còn trang tiếp theo hoặc trang trước.
- `totalCount`: tổng số kết quả nếu server cung cấp; field này có thể không có hoặc trả null nếu việc đếm quá tốn kém.

GraphQL không bắt buộc phải dùng tên `Connection`, `Edge` hay `PageInfo`. Đây là quy ước phổ biến theo Relay Connection Specification, hữu ích khi API cần mô hình pagination nhất quán.

`totalCount` trong ví dụ cũng dùng GraphQL `Int` nên có giới hạn 32-bit. Với tập dữ liệu lớn, hãy dùng custom scalar phù hợp hoặc không công bố tổng số nếu client không cần nó.

## 8. Cursor phải ổn định và không phụ thuộc offset

Cursor thường mã hóa các giá trị dùng để xác định vị trí trong thứ tự sắp xếp. Ví dụ danh sách sách sắp xếp `createdAt DESC, id DESC`, cursor có thể chứa:

~~~json
{
    "createdAt": "2026-11-20T08:30:00Z",
    "id": "book-101"
}
~~~

Để client không phụ thuộc cấu trúc nội bộ, server thường encode dữ liệu này thành chuỗi opaque, ví dụ Base64 URL-safe. Base64 chỉ là encoding, không phải mã hóa bảo mật và không ngăn client sửa cursor. Nếu cursor chứa dữ liệu nhạy cảm hoặc cần chống sửa đổi, hãy dùng token có chữ ký hoặc cơ chế xác thực tương ứng.

Một cursor tốt cần:

1. Đại diện cho một vị trí xác định trong thứ tự sắp xếp.
2. Dùng khóa sắp xếp ổn định, thường có thêm ID duy nhất làm tie-breaker.
3. Được validate khi decode; cursor sai định dạng hoặc không tương thích phải bị từ chối rõ ràng.
4. Gắn với filter và sort tương ứng nếu thay đổi các điều kiện đó có thể làm cursor mất ý nghĩa.
5. Không thay thế authorization; mọi request tiếp theo vẫn phải kiểm tra quyền truy cập dữ liệu.

Cursor/keyset giảm ảnh hưởng của việc chèn bản ghi ở đầu danh sách so với offset, nhưng không tự tạo snapshot nhất quán cho nhiều request. Nếu giá trị của cột sắp xếp thay đổi giữa các lần tải, một bản ghi vẫn có thể di chuyển qua vị trí cursor. Khi cần duyệt một tập dữ liệu bất biến, hãy dùng khóa sắp xếp không thay đổi hoặc thiết kế snapshot/version riêng.

Không nên tạo cursor chỉ từ số trang rồi gọi lại offset ở server nếu mục tiêu là tận dụng keyset pagination. Cách đó chỉ bọc offset trong một chuỗi, vẫn giữ nguyên các hạn chế của offset.

## 9. Truy vấn keyset pagination ở tầng repository

Với thứ tự `createdAt DESC, id DESC`, server có thể tìm các bản ghi đứng sau cursor bằng điều kiện so sánh theo cặp khóa. Pseudocode SQL:

~~~sql
SELECT id, title, created_at
FROM book
WHERE created_at < :cursorCreatedAt
   OR (created_at = :cursorCreatedAt AND id < :cursorId)
ORDER BY created_at DESC, id DESC
LIMIT :firstPlusOne
~~~

Khi chưa có cursor, bỏ điều kiện `WHERE` theo cursor và lấy từ đầu danh sách. Server đọc `first + 1` bản ghi:

- Nếu số bản ghi nhận được không vượt `first`, không còn trang tiếp theo.
- Nếu nhận được `first + 1`, bỏ phần tử dư và đặt `hasNextPage = true`.
- Cursor của mỗi edge được tạo từ các khóa sắp xếp của node tương ứng.

Ví dụ truy vấn trên giả định cả `created_at` và `id` có thứ tự giảm dần. Nếu sort tăng dần, toán tử so sánh cần đổi. Nếu sort theo nhiều cột, điều kiện keyset phải phản ánh đúng thứ tự từ điển của toàn bộ cột và tie-breaker.

Các cột dùng làm cursor key nên có giá trị xác định. Nếu cho phép `NULL` trong sort key, cần quy định rõ null ordering và đưa quy tắc đó vào cả SQL lẫn cursor codec.

Index database nên hỗ trợ các cột trong điều kiện và thứ tự sắp xếp, ví dụ index kết hợp `(created_at DESC, id DESC)` tùy database. Hãy kiểm tra execution plan thực tế; chỉ đổi sang cursor mà không có index phù hợp chưa chắc cải thiện hiệu năng.

## 10. Resolver cursor pagination trong Spring for GraphQL

Resolver nhận `first` và `after`, kiểm tra giới hạn, decode cursor rồi gọi service:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookConnectionController {

    private static final int DEFAULT_FIRST = 20;
    private static final int MAX_FIRST = 100;

    private final BookConnectionService bookService;
    private final BookCursorCodec cursorCodec;

    public BookConnectionController(
            BookConnectionService bookService,
            BookCursorCodec cursorCodec
    ) {
        this.bookService = bookService;
        this.cursorCodec = cursorCodec;
    }

    @QueryMapping
    public BookConnection books(
            @Argument("first") Integer first,
            @Argument("after") String after
    ) {
        int limit = first != null ? first : DEFAULT_FIRST;
        if (limit < 1 || limit > MAX_FIRST) {
            throw new IllegalArgumentException(
                    "first must be between 1 and " + MAX_FIRST
            );
        }

        BookCursor cursor = after != null
                ? cursorCodec.decode(after)
                : null;

        return bookService.findAfter(cursor, limit);
    }
}
~~~

Các kiểu `BookConnectionService`, `BookCursorCodec` và `BookCursor` là thành phần do ứng dụng định nghĩa. Service chịu trách nhiệm truy vấn keyset và tạo `edges` cùng `pageInfo`; codec chịu trách nhiệm encode/decode cursor và xác thực cấu trúc của nó.

Resolver giữ nhiệm vụ điều phối: bind argument, áp dụng giới hạn và chuyển cursor đã kiểm tra đến service. Không đặt SQL hoặc logic encode cursor trực tiếp trong controller.

## 11. Query cursor pagination từ client

Request đầu tiên:

~~~graphql
query FirstBooks {
    books(first: 20) {
        edges {
            cursor
            node {
                id
                title
            }
        }
        pageInfo {
            hasNextPage
            hasPreviousPage
            startCursor
            endCursor
        }
    }
}
~~~

Sau khi nhận response, client lấy `endCursor` và gửi vào `after` để tải trang tiếp:

~~~graphql
query NextBooks($after: String!) {
    books(first: 20, after: $after) {
        edges {
            cursor
            node {
                id
                title
            }
        }
        pageInfo {
            hasNextPage
            endCursor
        }
    }
}
~~~

Variables của request tiếp theo:

~~~json
{
    "after": "eyJjcmVhdGVkQXQiOiIyMDI2LTExLTIwVDA4OjMwOjAwWiIsImlkIjoiYm9vay0xMDEifQ"
}
~~~

Chuỗi trên chỉ là ví dụ minh họa cursor opaque. Client nên xem cursor như token do server cấp, không tự giải mã hoặc tự tạo cursor. Khi đổi filter hoặc sort, client thường nên bắt đầu lại từ trang đầu vì cursor cũ có thể không còn phù hợp.

## 12. Chọn Page, Slice hay cursor/keyset?

| Tiêu chí | Offset với Page | Offset với Slice | Cursor/keyset |
| --- | --- | --- | --- |
| Nhảy đến trang bất kỳ | Thuận tiện | Thuận tiện | Không phải mục tiêu chính |
| Biết tổng số phần tử | Có | Không mặc định | Không mặc định; count có thể bổ sung |
| Tải thêm/cuộn vô hạn | Có thể dùng | Phù hợp | Rất phù hợp |
| Trang rất sâu | Có thể chậm | Có thể chậm | Thường hiệu quả hơn khi có index phù hợp |
| Dữ liệu thay đổi giữa các lần gọi | Có thể lặp hoặc bỏ sót phần tử | Có thể lặp hoặc bỏ sót phần tử | Ổn định hơn nếu cursor và thứ tự được thiết kế đúng |
| Độ phức tạp triển khai | Thấp | Thấp | Cao hơn: cần encode/decode và kiểm tra cursor |

Chọn `Page` khi giao diện cần số trang và tổng số kết quả. Chọn `Slice` khi chỉ cần biết còn trang tiếp theo. Chọn cursor/keyset khi client tải tiếp theo vị trí cuối, dữ liệu lớn hoặc offset sâu trở thành vấn đề hiệu năng.

## 13. Kết hợp filter, sort và pagination

Filter phải được áp dụng trước khi phân trang. Ví dụ query tìm sách theo trạng thái:

~~~graphql
enum BookStatus {
    DRAFT
    PUBLISHED
    ARCHIVED
}

input BookFilter {
    keyword: String
    status: BookStatus
}

type Query {
    books(
        filter: BookFilter
        page: Int! = 0
        size: Int! = 20
    ): BookPage!
}
~~~

Service cần thực hiện theo trình tự logic:

1. Xác định phạm vi dữ liệu người dùng được phép xem.
2. Áp dụng filter theo keyword, status hoặc điều kiện nghiệp vụ.
3. Áp dụng thứ tự sort đã được allowlist.
4. Áp dụng page/size hoặc cursor để giới hạn kết quả.
5. Tạo metadata phân trang phù hợp với chiến lược đã chọn.

Với cursor pagination, cursor cần tương thích với filter và sort. Nếu client gửi cursor được tạo cho `CREATED_AT_DESC` nhưng request sau đổi sang `TITLE_ASC`, server nên từ chối cursor không phù hợp hoặc yêu cầu client bắt đầu lại.

Không nhận trực tiếp tên cột SQL hoặc thuộc tính entity tùy ý từ client làm sort key. Dùng enum hoặc allowlist để tránh lộ field nội bộ và tránh tạo truy vấn không mong muốn.

## 14. Kiểm thử pagination bằng GraphQlTester

Có thể dùng `@GraphQlTest` để kiểm tra resolver và schema mà không cần khởi động toàn bộ ứng dụng. Ví dụ kiểm tra offset pagination:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import java.util.List;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;

@GraphQlTest(BookQueryController.class)
class BookPaginationTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @Test
    void returnsRequestedPage() {
        List<Book> books = List.of(
                new Book("book-1", "GraphQL basics", "2026-01-02T00:00:00Z"),
                new Book("book-2", "Spring GraphQL", "2026-01-01T00:00:00Z")
        );
        Pageable pageable = PageRequest.of(
                1, 2,
                Sort.by(Sort.Direction.DESC, "createdAt")
                        .and(Sort.by(Sort.Direction.DESC, "id"))
        );
        Page<Book> page = new PageImpl<>(books, pageable, 5);
        given(bookService.findAll(any(Pageable.class))).willReturn(page);

        GraphQlTester.Response response = graphQlTester.document("""
                query Books($page: Int!, $size: Int!, $sort: BookSort!) {
                    books(page: $page, size: $size, sort: $sort) {
                        content { id title }
                        page
                        size
                        totalElements
                        totalPages
                        hasNext
                    }
                }
                """)
            .variable("page", 1)
            .variable("size", 2)
            .variable("sort", "CREATED_AT_DESC")
            .execute();

        response.errors().verify();
        response.path("books.content").entityList(Book.class).hasSize(2);
        response.path("books.page").entity(Integer.class).isEqualTo(1);
        response.path("books.totalElements").entity(Integer.class).isEqualTo(5);
        response.path("books.hasNext").entity(Boolean.class).isEqualTo(true);
    }
}
~~~

`BookService` được mock bằng `@MockitoBean`; dữ liệu trả về mô phỏng trang thứ hai với tổng cộng năm phần tử. Các assertion đọc content và metadata từ cùng một GraphQL response.

Các trường hợp cần kiểm tra:

1. Trang đầu có dữ liệu và trang cuối có `hasNext = false`.
2. Trang vượt quá số trang hiện có trả danh sách rỗng hoặc hành vi đã định nghĩa.
3. `page` âm, `size` bằng 0 hoặc vượt giới hạn bị từ chối.
4. Sort chỉ chấp nhận các giá trị trong enum allowlist.
5. Filter được áp dụng trước khi pagination.
6. Cursor hợp lệ trả đúng phần tử tiếp theo; cursor sai format hoặc sai filter/sort bị từ chối.
7. Hai request cursor liên tiếp không lặp phần tử khi có bản ghi mới được chèn ở đầu danh sách.
8. Người dùng không thể dùng pagination để đọc dữ liệu ngoài phạm vi được phép.

## 15. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Client yêu cầu page size quá lớn | Resolver không giới hạn `size` hoặc `first` | Đặt giá trị tối đa ở server và trả lỗi input rõ ràng |
| Trang có phần tử lặp hoặc bị bỏ qua | Sort không ổn định hoặc dữ liệu thay đổi giữa các request offset | Thêm tie-breaker duy nhất hoặc dùng cursor/keyset |
| Trang sâu phản hồi chậm | Offset lớn và index không phù hợp | Dùng keyset/cursor và kiểm tra execution plan |
| `totalElements` tốn kém | `Page` cần truy vấn count trên tập dữ liệu lớn | Dùng `Slice` hoặc bỏ `totalCount` nếu UI không cần |
| Cursor không còn hợp lệ | Cursor được tạo theo sort/filter khác hoặc format cũ | Validate cursor, gắn phiên bản và fingerprint filter/sort |
| Cursor bị client sửa | Chỉ Base64 encode nhưng không kiểm tra tính toàn vẹn | Dùng chữ ký hoặc token xác thực nếu cần chống sửa đổi |
| GraphQL báo lỗi khi sort | Client truyền giá trị enum không có trong schema | Kiểm tra enum và xử lý giá trị được hỗ trợ |
| Response metadata sai | Ánh xạ nhầm page, size, total hoặc hasNext | Viết test cho trang đầu, giữa và cuối |

## 16. Bảo mật và tối ưu chi phí pagination

Pagination không thay thế authorization. Mỗi request trang tiếp theo phải áp dụng lại phạm vi dữ liệu người dùng được phép xem. Không tin cursor như bằng chứng người dùng có quyền đọc một bản ghi; cursor chỉ biểu diễn vị trí.

Giới hạn page size ở server ngay cả khi schema đã có default. Client có thể truyền giá trị tối đa mà schema cho phép, nên resolver/service cần kiểm tra giới hạn cứng. Cũng cần giới hạn độ sâu, độ phức tạp và số lượng field liên kết trong một operation; một trang nhỏ nhưng mỗi phần tử kéo theo nhiều quan hệ vẫn có thể tạo truy vấn rất tốn kém.

Khi pagination đi cùng `@SchemaMapping` hoặc `@BatchMapping`, hãy kiểm tra N+1 ở các field con. Giới hạn số `Book` không tự giới hạn số query phát sinh nếu mỗi `Book` tải `author`, `reviews` hoặc `publisher` riêng lẻ. DataLoader và batching giúp gom các lần tải dữ liệu liên quan.

## 17. Quy trình triển khai query pagination

Khi bổ sung pagination cho một GraphQL query:

1. Xác định giao diện cần nhảy trang, tổng số kết quả hay chỉ cần tải tiếp.
2. Chọn offset `Page`/`Slice` hoặc cursor/keyset theo quy mô và đặc điểm thay đổi dữ liệu.
3. Thiết kế SDL với argument, default value và wrapper type rõ ràng.
4. Dùng `@QueryMapping` và `@Argument` để bind dữ liệu; validate page size và sort ở server.
5. Đưa truy vấn vào service/repository, áp dụng authorization và filter trước pagination.
6. Với offset, dùng thứ tự ổn định và đánh giá chi phí count/offset. Với cursor, tạo cursor opaque từ toàn bộ sort key có tie-breaker duy nhất.
7. Kiểm thử trang đầu, trang cuối, input sai, dữ liệu thay đổi và quyền truy cập bằng `GraphQlTester`.
8. Theo dõi thời gian truy vấn, số bản ghi đọc, count query và các resolver field con để tối ưu tiếp.

Pagination là một phần của hợp đồng GraphQL. Thiết kế tốt giúp client lấy dữ liệu theo nhu cầu, server kiểm soát tải và API duy trì thứ tự kết quả ổn định khi dữ liệu tăng lên.

## Tài liệu tham khảo

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring Data Commons — Paging and Sorting](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html)
- [Spring Data Commons — Scrolling](https://docs.spring.io/spring-data/commons/reference/repositories/scrolling.html)
- [Relay — Cursor Connections Specification](https://relay.dev/graphql/connections.htm)
