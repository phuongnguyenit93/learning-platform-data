# Pagination trong Spring for GraphQL

Pagination giúp GraphQL API trả dữ liệu theo từng phần thay vì tải toàn bộ collection trong một request. Với Spring for GraphQL, resolver nhận các tham số phân trang từ GraphQL arguments, chuyển chúng thành `Pageable` hoặc cursor, rồi gọi service/repository để chỉ lấy phần dữ liệu cần thiết.

GraphQL không bắt buộc một chuẩn pagination duy nhất. Hai cách phổ biến là **offset pagination** với `page`/`size` và **cursor pagination** với `first`/`after`. Offset dễ triển khai, hỗ trợ nhảy đến một trang bất kỳ và thường phù hợp với màn hình quản trị. Cursor/keyset phù hợp hơn với collection lớn, dữ liệu thay đổi thường xuyên hoặc luồng tải tiếp trang.

## 1. Vì sao cần pagination?

Giả sử một API có query trả về tất cả sách:

~~~graphql
type Query {
    books: [Book!]!
}
~~~

Khi số lượng sách tăng lên hàng trăm nghìn, một request có thể tạo ra:

- Truy vấn database đọc quá nhiều hàng.
- Response JSON lớn và tốn băng thông.
- Thời gian serialize và deserialize cao.
- Tăng heap và áp lực garbage collection.
- Nhiều field con được resolve, làm tăng nguy cơ N+1.
- Request chiếm connection và tài nguyên server lâu hơn.

Pagination giới hạn số record trả về trong mỗi lần thực thi. Tuy nhiên, chỉ thêm `first` hoặc `size` vào SDL chưa đủ: resolver và repository phải áp dụng giới hạn ngay tại database. Không nên tải toàn bộ dữ liệu vào Java rồi mới gọi `subList` để cắt trang.

## 2. Chọn chiến lược pagination

| Chiến lược | GraphQL arguments thường dùng | Ưu điểm | Hạn chế |
| --- | --- | --- | --- |
| Offset/page-based | `page`, `size`, `sort` | Dễ hiểu, hỗ trợ nhảy đến trang bất kỳ | Trang sâu có thể chậm; dữ liệu thay đổi có thể làm trùng hoặc bỏ sót record |
| Cursor/keyset | `first`, `after` hoặc `last`, `before` | Hiệu quả với tập dữ liệu lớn; tiếp tục từ vị trí ổn định | Không nhảy trực tiếp đến trang bất kỳ; cần cursor và thứ tự sắp xếp ổn định |
| Relay connection | `first`, `after`, `last`, `before` | Response chuẩn hóa bằng `edges`, `cursor`, `pageInfo` | Cần triển khai connection và cursor logic rõ ràng |

Relay connection là một shape response phổ biến cho cursor pagination. Nó không tự động được tạo chỉ vì ứng dụng dùng Spring for GraphQL; schema, resolver và cursor logic vẫn do ứng dụng định nghĩa.

## 3. Offset pagination với page và size

Offset pagination thường phù hợp khi giao diện cần số trang, tổng số phần tử hoặc cho phép người dùng nhảy tới một trang cụ thể.

Ví dụ schema:

~~~graphql
enum BookSortField {
    TITLE
    CREATED_AT
}

enum SortDirection {
    ASC
    DESC
}

type Query {
    books(
        page: Int = 0
        size: Int = 20
        sortBy: BookSortField = CREATED_AT
        direction: SortDirection = DESC
    ): BookPage!
}

type BookPage {
    items: [Book!]!
    page: Int!
    size: Int!
    totalElements: Int!
    totalPages: Int!
    hasNext: Boolean!
    hasPrevious: Boolean!
}

type Book {
    id: ID!
    title: String!
    author: Author
}

type Author {
    id: ID!
    name: String!
}
~~~

GraphQL page index thường bắt đầu từ `0`, tương tự Spring Data `PageRequest`. Nếu API muốn đánh số trang từ `1`, hãy chuyển đổi nhất quán ở resolver và ghi rõ trong schema documentation.

Trong các ví dụ bên dưới, `Book` là JPA entity có `Long id`, `String title`, `Long authorId`, `String tenantId` và `Instant createdAt`. Field GraphQL `author` được resolve từ `authorId` bằng resolver/DataLoader; các thuộc tính `tenantId`, `authorId` và `createdAt` không nhất thiết phải expose cho client.

~~~java
import java.time.Instant;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "book")
public class Book {

    @Id
    private Long id;
    private String title;
    private Long authorId;
    private String tenantId;
    private Instant createdAt;

    protected Book() {}

    public Book(Long id, String title, Long authorId,
            String tenantId, Instant createdAt) {
        this.id = id;
        this.title = title;
        this.authorId = authorId;
        this.tenantId = tenantId;
        this.createdAt = createdAt;
    }

    public Long getId() { return id; }
    public String getTitle() { return title; }
    public Long getAuthorId() { return authorId; }
    public String getTenantId() { return tenantId; }
    public Instant getCreatedAt() { return createdAt; }
}
~~~

## 4. Chuyển GraphQL arguments thành Pageable

Spring Data cung cấp `Pageable`, `PageRequest`, `Sort`, `Page` và `Slice`. Resolver có thể tạo `Pageable` từ các arguments rồi truyền xuống service.

Enum Java tương ứng với enum trong SDL:

~~~java
public enum BookSortField {
    TITLE,
    CREATED_AT
}

public enum SortDirection {
    ASC,
    DESC
}
~~~

Record mô tả response:

~~~java
import java.util.List;

public record BookPage(
        List<Book> items,
        int page,
        int size,
        int totalElements,
        int totalPages,
        boolean hasNext,
        boolean hasPrevious
) {}
~~~

Repository và service:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository extends JpaRepository<Book, Long> {
    Page<Book> findByTenantId(String tenantId, Pageable pageable);
}
~~~

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;

@Service
public class BookService {

    private final BookRepository repository;

    public BookService(BookRepository repository) {
        this.repository = repository;
    }

    public Page<Book> findVisibleBooks(String tenantId, Pageable pageable) {
        return repository.findByTenantId(tenantId, pageable);
    }
}
~~~

`tenantId` ở đây được lấy từ một abstraction chỉ đọc tenant của principal đã xác thực:

~~~java
public interface CurrentTenantProvider {
    String currentTenantId();
}
~~~

Implementation của `CurrentTenantProvider` có thể đọc tenant từ Spring Security principal hoặc context đã được xác thực. Điều kiện tenant được áp dụng ngay trong repository query trước khi database phân trang. Với ứng dụng không multi-tenant, có thể bỏ tham số này và dùng filter dữ liệu tương ứng của domain.

Controller:

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

    private final BookService bookService;
    private final CurrentTenantProvider tenantProvider;

    public BookQueryController(BookService bookService,
            CurrentTenantProvider tenantProvider) {
        this.bookService = bookService;
        this.tenantProvider = tenantProvider;
    }

    @QueryMapping
    public BookPage books(
            @Argument Integer page,
            @Argument Integer size,
            @Argument BookSortField sortBy,
            @Argument SortDirection direction
    ) {
        int pageNumber = page == null ? 0 : page;
        int pageSize = size == null ? 20 : size;

        if (pageNumber < 0) {
            throw new InvalidPaginationException("page must be zero or greater");
        }
        if (pageSize < 1 || pageSize > 100) {
            throw new InvalidPaginationException("size must be between 1 and 100");
        }

        BookSortField field = sortBy == null ? BookSortField.CREATED_AT : sortBy;
        SortDirection order = direction == null ? SortDirection.DESC : direction;

        String property = switch (field) {
            case TITLE -> "title";
            case CREATED_AT -> "createdAt";
        };
        Sort.Direction sortDirection = order == SortDirection.ASC
                ? Sort.Direction.ASC
                : Sort.Direction.DESC;

        Sort sort = Sort.by(sortDirection, property)
                .and(Sort.by(sortDirection, "id"));
        Pageable pageable = PageRequest.of(pageNumber, pageSize, sort);

        Page<Book> result = bookService.findVisibleBooks(
                tenantProvider.currentTenantId(), pageable);

        return new BookPage(
                result.getContent(),
                result.getNumber(),
                result.getSize(),
                Math.toIntExact(result.getTotalElements()),
                result.getTotalPages(),
                result.hasNext(),
                result.hasPrevious()
        );
    }
}
~~~

`CurrentTenantProvider` là abstraction của ứng dụng để lấy tenant từ principal đã xác thực. Controller không nhận tenant ID từ GraphQL argument, nên client không thể tự đổi tenant bằng cách sửa query.

Đầu vào phân trang sai nên được ánh xạ thành GraphQL error dành cho client, ví dụ `BAD_REQUEST`, thay vì để lỗi `IllegalArgumentException` trở thành lỗi nội bộ. Phần sau minh họa một exception và handler dùng chung cho page/size và cursor.

~~~java
public class InvalidPaginationException extends RuntimeException {
    public InvalidPaginationException(String message) {
        super(message);
    }

    public InvalidPaginationException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;

import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

import java.util.Map;

@ControllerAdvice
public class PaginationExceptionAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleInvalidPagination(
            InvalidPaginationException exception,
            DataFetchingEnvironment environment
    ) {
        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.BAD_REQUEST)
                .message(exception.getMessage())
                .extensions(Map.of("code", "INVALID_PAGINATION"))
                .build();
    }
}
~~~

## 5. Vì sao phải giới hạn page size và allow-list sort field?

Không để client tùy ý yêu cầu `size = 1000000`. Kích thước trang quá lớn có thể tạo query nặng, response lớn và tiêu tốn bộ nhớ. Luôn đặt giới hạn tối đa ở server, kể cả khi SDL có default.

Không truyền trực tiếp một string do client cung cấp vào `Sort.by(...)`:

~~~java
// Không nên nhận raw property name từ client.
Sort sort = Sort.by(clientProvidedSortField);
~~~

Thay vào đó, dùng GraphQL enum hoặc allow-list và ánh xạ sang property Java cố định. Cách này tránh lộ các field nội bộ, tránh sort theo quan hệ tốn kém và giúp schema thể hiện rõ các lựa chọn được hỗ trợ.

Thứ tự sắp xếp cần ổn định. Nếu nhiều sách có cùng `createdAt`, thêm một unique tie-breaker như `id`. Nếu không, hai request ở trang liền kề có thể nhận record trùng hoặc bỏ sót khi database trả các hàng đồng hạng theo thứ tự khác nhau.

## 6. Page và Slice khác nhau thế nào?

Spring Data có hai abstraction thường dùng:

| Kiểu | Thông tin cung cấp | Chi phí thường gặp |
| --- | --- | --- |
| `Page<T>` | Content, page metadata, total elements, total pages | Thường cần thêm count query để biết tổng số phần tử |
| `Slice<T>` | Content, hasNext, hasPrevious | Có thể chỉ cần lấy thêm một phần tử để xác định còn trang sau |

Nếu UI cần hiển thị “trang 2 trên 50” hoặc tổng số kết quả, `Page<T>` phù hợp. Nếu UI chỉ có nút “Load more”, `Slice<T>` thường tiết kiệm hơn vì không cần count toàn bộ kết quả.

Count query có thể đắt với bảng lớn, join phức tạp hoặc filter nhiều điều kiện. Không nên expose `totalElements` chỉ vì Spring Data `Page` có sẵn thuộc tính đó; hãy cân nhắc liệu client có thực sự cần tổng số.

## 7. Cẩn thận với GraphQL Int và totalElements

GraphQL built-in scalar `Int` là số nguyên signed 32-bit. `Page.getTotalElements()` của Spring Data là `long`. `Math.toIntExact(...)` trong ví dụ sẽ ném lỗi nếu số lượng vượt phạm vi GraphQL `Int`.

Nếu dữ liệu có thể vượt giới hạn đó, hãy chọn một trong các cách:

- Đăng ký custom scalar `Long`/`BigInt` và dùng scalar nhất quán ở client.
- Trả tổng số dưới dạng `String` nếu hợp đồng API chấp nhận kiểu biểu diễn đó.
- Bỏ `totalElements`, chỉ trả `hasNext` hoặc `pageInfo`.

Cursor connection thường không cần total count, vì count có thể tốn kém và không cần thiết để tải trang kế tiếp.

## 8. Offset pagination có giới hạn ở trang sâu

Offset query thường được database thực hiện theo ý nghĩa `OFFSET n LIMIT m`. Với page index lớn, database vẫn có thể phải duyệt hoặc bỏ qua nhiều hàng trước khi lấy được phần cần thiết.

Ví dụ:

~~~sql
SELECT id, title, created_at
FROM book
WHERE tenant_id = ?
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 200000;
~~~

Truy vấn trang sâu có thể tốn thời gian hơn nhiều so với trang đầu. Ngoài ra, khi record được thêm hoặc xóa giữa hai request, offset có thể làm record dịch chuyển vị trí: client có thể nhìn thấy một record hai lần hoặc bỏ qua một record.

Offset vẫn hợp lý với collection vừa phải, dữ liệu ít thay đổi và UI cần nhảy đến số trang. Với feed, audit log hoặc collection lớn, cân nhắc cursor/keyset pagination.

## 9. Cursor pagination và Relay connection

Cursor pagination định vị trang kế tiếp dựa trên một record cuối cùng đã nhận thay vì số lượng record cần bỏ qua. Relay connection thường có dạng:

~~~graphql
extend type Query {
    bookConnection(first: Int = 20, after: String): BookConnection!
}

type BookConnection {
    edges: [BookEdge!]!
    pageInfo: PageInfo!
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
~~~

`edges` chứa từng record cùng cursor. `pageInfo` cho biết còn trang trước/sau và cursor đầu/cuối của trang hiện tại. Client dùng `endCursor` của response trước làm `after` trong request tiếp theo.

Ví dụ query:

~~~graphql
query FirstBooks {
    bookConnection(first: 20) {
        edges {
            cursor
            node { id title }
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

Trang kế tiếp:

~~~graphql
query NextBooks($after: String!) {
    bookConnection(first: 20, after: $after) {
        edges {
            cursor
            node { id title }
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

## 10. Thiết kế cursor ổn định

Cursor phải đại diện cho vị trí trong thứ tự sắp xếp. Chỉ dùng `id` là đủ khi collection được sắp xếp duy nhất theo ID. Nếu sort theo `createdAt`, cursor cần cả `createdAt` và unique tie-breaker `id`.

Model:

~~~java
import java.time.Instant;

public record BookCursor(Instant createdAt, Long id) {}
~~~

Codec đơn giản dùng Base64 URL-safe:

~~~java
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Base64;

public class BookCursorCodec {

    public String encode(Book book) {
        String value = book.getCreatedAt() + "|" + book.getId();
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(value.getBytes(StandardCharsets.UTF_8));
    }

    public BookCursor decode(String cursor) {
        try {
            String value = new String(
                    Base64.getUrlDecoder().decode(cursor),
                    StandardCharsets.UTF_8
            );
            int separator = value.indexOf('|');
            if (separator <= 0 || separator == value.length() - 1) {
                throw new InvalidPaginationException("after cursor is invalid");
            }
            Instant createdAt = Instant.parse(value.substring(0, separator));
            Long id = Long.valueOf(value.substring(separator + 1));
            return new BookCursor(createdAt, id);
        }
        catch (RuntimeException exception) {
            if (exception instanceof InvalidPaginationException invalid) {
                throw invalid;
            }
            throw new InvalidPaginationException("after cursor is invalid", exception);
        }
    }
}
~~~

Base64 chỉ giúp biểu diễn cursor dưới dạng chuỗi opaque, không mã hóa hoặc bảo vệ tính toàn vẹn. Client có thể decode và sửa nội dung. Nếu cursor cần chống giả mạo, hãy ký payload bằng HMAC hoặc dùng token được bảo vệ ở server. Dù cursor được ký, authorization và tenant filter vẫn phải được áp dụng trong database query.

Cursor nên gắn với phiên bản thuật toán sort và filter scope. Nếu client đổi filter hoặc sort giữa các trang, cursor cũ có thể không còn đại diện cho cùng một thứ tự. Có thể đưa fingerprint của filter/sort vào payload và từ chối cursor không khớp.

Service mẫu bên dưới cố định thứ tự `createdAt DESC, id DESC`. Nếu API cho phép client chọn sort khác, cần tạo keyset predicate và cursor payload tương ứng cho từng sort mode; không thể dùng cursor chỉ chứa `createdAt` và `id` cho một thứ tự khác.

## 11. Keyset query với tie-breaker

Giả sử trang được sắp xếp giảm dần theo `createdAt`, sau đó giảm dần theo `id`. Record tiếp theo phải thỏa:

~~~sql
WHERE tenant_id = :tenantId
  AND (
       created_at < :createdAt
       OR (created_at = :createdAt AND id < :id)
  )
ORDER BY created_at DESC, id DESC
LIMIT :limit;
~~~

Điều kiện tuple đảm bảo các record có cùng timestamp vẫn được phân biệt bằng ID. Với sort tăng dần, toán tử so sánh và thứ tự cần được đảo tương ứng. Nếu sort theo nhiều cột, cursor phải mang đủ giá trị để tái tạo thứ tự tổng thể.

Index nên hỗ trợ cả filter và thứ tự keyset. Với query trên, một index có thể có dạng:

~~~sql
CREATE INDEX idx_book_tenant_created_id
    ON book (tenant_id, created_at DESC, id DESC);
~~~

Cú pháp và mức độ tận dụng thứ tự index phụ thuộc database engine. Hãy kiểm tra `EXPLAIN`/query plan trên hệ quản trị đang dùng; nếu hỗ trợ nhiều sort mode, có thể cần index khác cho từng đường truy vấn quan trọng. Không tạo index chỉ dựa trên ví dụ mà chưa xem workload và chi phí ghi dữ liệu.

Repository Spring Data JPA có thể khai báo custom query:

~~~java
import java.time.Instant;
import java.util.List;

import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface BookCursorRepository extends JpaRepository<Book, Long> {

    List<Book> findByTenantIdOrderByCreatedAtDescIdDesc(
            String tenantId,
            Pageable pageable
    );

    @Query("""
            select b from Book b
            where b.tenantId = :tenantId
              and (
                    b.createdAt < :createdAt
                    or (b.createdAt = :createdAt and b.id < :id)
              )
            order by b.createdAt desc, b.id desc
            """)
    List<Book> findAfter(
            @Param("tenantId") String tenantId,
            @Param("createdAt") Instant createdAt,
            @Param("id") Long id,
            Pageable limit
    );
}
~~~

Với trang đầu, dùng derived query có thứ tự cố định. Với trang tiếp theo, dùng keyset predicate trong `findAfter`. `Pageable` ở đây chỉ giới hạn số hàng; thứ tự đã được cố định trong query.

## 12. Lấy thêm một record để xác định hasNextPage

Khi client yêu cầu `first = 20`, service tải tối đa 21 record. Nếu có record thứ 21, trang hiện tại còn trang tiếp theo. Record dư không được đưa vào `edges`.

Response model:

~~~java
import java.util.List;

public record BookEdge(String cursor, Book node) {}

public record PageInfo(
        boolean hasNextPage,
        boolean hasPreviousPage,
        String startCursor,
        String endCursor
) {}

public record BookConnection(List<BookEdge> edges, PageInfo pageInfo) {}
~~~

Service:

~~~java
import java.util.List;

import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;

@Service
public class BookConnectionService {

    private final BookCursorRepository repository;
    private final BookCursorCodec cursorCodec;

    public BookConnectionService(
            BookCursorRepository repository,
            BookCursorCodec cursorCodec
    ) {
        this.repository = repository;
        this.cursorCodec = cursorCodec;
    }

    public BookConnection findNextPage(
            String tenantId,
            int first,
            String after
    ) {
        if (first < 1 || first > 100) {
            throw new InvalidPaginationException("first must be between 1 and 100");
        }

        int fetchSize = first + 1;
        List<Book> rows;

        if (after == null || after.isBlank()) {
            rows = repository.findByTenantIdOrderByCreatedAtDescIdDesc(
                    tenantId,
                    PageRequest.of(0, fetchSize)
            );
        }
        else {
            BookCursor cursor = cursorCodec.decode(after);
            rows = repository.findAfter(
                    tenantId,
                    cursor.createdAt(),
                    cursor.id(),
                    PageRequest.of(0, fetchSize)
            );
        }

        boolean hasNextPage = rows.size() > first;
        List<Book> pageItems = hasNextPage
                ? rows.subList(0, first)
                : rows;

        List<BookEdge> edges = pageItems.stream()
                .map(book -> new BookEdge(cursorCodec.encode(book), book))
                .toList();

        String startCursor = edges.isEmpty() ? null : edges.get(0).cursor();
        String endCursor = edges.isEmpty() ? null : edges.get(edges.size() - 1).cursor();

        boolean hasPreviousPage = after != null && !after.isBlank();
        return new BookConnection(
                edges,
                new PageInfo(hasNextPage, hasPreviousPage, startCursor, endCursor)
        );
    }
}
~~~

Ví dụ trên minh họa forward pagination. `hasPreviousPage` được suy ra từ việc request có cursor `after`, với giả định cursor hợp lệ và thuộc cùng connection scope. Nếu cần giá trị chính xác trong mọi tình huống, hãy xác minh cursor thuộc tenant/filter hiện tại và kiểm tra có record trước cursor hay không.

## 13. Resolver cho cursor connection

Resolver chỉ nhận arguments và context, sau đó giao việc truy vấn cho service:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookConnectionController {

    private final BookConnectionService connectionService;
    private final CurrentTenantProvider tenantProvider;

    public BookConnectionController(BookConnectionService connectionService,
            CurrentTenantProvider tenantProvider) {
        this.connectionService = connectionService;
        this.tenantProvider = tenantProvider;
    }

    @QueryMapping
    public BookConnection bookConnection(
            @Argument Integer first,
            @Argument String after
    ) {
        int pageSize = first == null ? 20 : first;
        return connectionService.findNextPage(
                tenantProvider.currentTenantId(), pageSize, after);
    }
}
~~~

Client dùng `endCursor` để lấy trang tiếp theo:

~~~graphql
query NextBooks($first: Int!, $after: String) {
    bookConnection(first: $first, after: $after) {
        edges {
            cursor
            node { id title }
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

Variables của request đầu có thể là `{ "first": 20 }`. Request tiếp theo truyền `{ "first": 20, "after": "<endCursor-cua-trang-truoc>" }`.

## 14. Backward pagination với last và before

Relay connection còn hỗ trợ `last` và `before` để tải các record đứng trước cursor. Với thứ tự chuẩn `createdAt DESC, id DESC`, truy vấn backward thường cần đảo chiều predicate và sort khi đọc database, lấy `last + 1` record, rồi đảo list lại về thứ tự chuẩn trước khi tạo edges.

Ví dụ ý tưởng:

~~~sql
WHERE tenant_id = :tenantId
  AND (
       created_at > :createdAt
       OR (created_at = :createdAt AND id > :id)
  )
ORDER BY created_at ASC, id ASC
LIMIT :limit;
~~~

Sau khi lấy kết quả, đảo thứ tự list trước khi trả về để client luôn nhìn thấy cùng một thứ tự canonical. Cần test kỹ `hasPreviousPage`, `hasNextPage`, `startCursor` và `endCursor` khi trang rỗng hoặc chỉ có một phần tử.

Nếu ứng dụng chỉ cần tải tiếp về phía trước, đừng thêm `last`/`before` khi chưa có use case rõ ràng. Hỗ trợ hai chiều làm cursor service và test phức tạp hơn.

## 15. Pagination và filter phải được áp dụng cùng nhau

Filter, tenant scope và authorization phải được áp dụng trước khi phân trang. Không tải một trang toàn cục rồi lọc bỏ record không thuộc tenant trong Java:

~~~java
// Không nên: có thể trả trang thiếu phần tử và làm sai page metadata.
Page<Book> page = repository.findAll(pageable);
List<Book> visible = page.getContent().stream()
        .filter(book -> book.tenantId().equals(tenantId))
        .toList();
~~~

Thay vào đó, thêm điều kiện tenant vào database query trước `LIMIT/OFFSET` hoặc keyset predicate. Cách này tránh lộ dữ liệu và bảo đảm page metadata phản ánh đúng tập kết quả người dùng được phép xem.

Cursor cũng cần được ràng buộc với filter/sort hiện tại. Nếu cursor được tạo cho `status = PUBLISHED` nhưng request tiếp theo đổi sang `status = DRAFT`, vị trí cursor có thể không còn ý nghĩa. Có thể encode filter fingerprint trong cursor hoặc yêu cầu client dùng lại cùng filter variables.

## 16. Pagination không tự giải quyết N+1

Pagination giới hạn số parent object. Nhưng nếu mỗi parent có field con cần truy vấn riêng, query vẫn có thể phát sinh N+1 trong phạm vi một trang.

Ví dụ trang có 20 sách và mỗi sách cần tác giả:

- Pagination tải 20 sách.
- Resolver naive có thể gọi 20 truy vấn tác giả.
- `DataLoader` hoặc `@BatchMapping` gom các author ID thành một batch.

Vì vậy, cần kết hợp pagination với DataLoader cho quan hệ lồng nhau. Kiểm tra cả số parent rows lẫn số batch/database calls trong test và profiling.

## 17. Kiểm thử offset pagination bằng GraphQlTester

Test nên kiểm tra cả response lẫn `Pageable` được truyền xuống service:

~~~java
import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.graphql.test.tester.GraphQlTester;

import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;

@GraphQlTest(BookQueryController.class)
class BookPaginationTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @MockitoBean
    CurrentTenantProvider tenantProvider;

    @Test
    void appliesPageSizeAndStableSort() {
        given(tenantProvider.currentTenantId()).willReturn("tenant-a");
        given(bookService.findVisibleBooks(eq("tenant-a"), org.mockito.ArgumentMatchers.any()))
                .willReturn(new PageImpl<>(
                        List.of(new Book(21L, "Spring GraphQL", 10L, "tenant-a",
                                Instant.parse("2026-01-01T00:00:00Z"))),
                        PageRequest.of(1, 10),
                        21
                ));

        graphQlTester.document("""
                query {
                    books(page: 1, size: 10, sortBy: CREATED_AT, direction: DESC) {
                        items { id title }
                        page
                        size
                        totalElements
                        totalPages
                        hasNext
                    }
                }
                """)
                .execute()
                .path("books.page")
                .entity(Integer.class)
                .isEqualTo(1);

        verify(bookService).findVisibleBooks(eq("tenant-a"), argThat(pageable ->
                pageable.getPageNumber() == 1
                        && pageable.getPageSize() == 10
                        && pageable.getSort().getOrderFor("createdAt").isDescending()
                        && pageable.getSort().getOrderFor("id").isDescending()
        ));
    }
}
~~~

Test mock `CurrentTenantProvider` để trả về tenant của principal hiện tại, nên không cần đưa tenant ID qua GraphQL arguments.

Các boundary test cần có:

- `page = 0`, `size = 1`.
- `page` âm bị từ chối.
- `size = 0` và `size` vượt giới hạn tối đa bị từ chối.
- `size` bị bỏ qua nhận default.
- Sort field không nằm trong enum không thể được bind.
- Sort luôn có tie-breaker duy nhất.
- Filter tenant được truyền xuống repository.
- Trang cuối có `hasNext = false`.

## 18. Kiểm thử cursor pagination

Với cursor pagination, cần kiểm tra rằng:

1. Trang đầu lấy tối đa `first + 1` record.
2. `hasNextPage` đúng khi có record dư.
3. `endCursor` của trang đầu có thể dùng cho request tiếp theo.
4. Trang tiếp theo không lặp lại record cuối của trang trước.
5. Record có cùng timestamp vẫn được sắp xếp ổn định nhờ ID tie-breaker.
6. Cursor không hợp lệ bị từ chối rõ ràng.
7. Tenant và filter được áp dụng ở cả trang đầu lẫn trang tiếp theo.

Ví dụ kiểm tra hai trang bằng `GraphQlTester`:

~~~java
@Test
void loadsNextCursorPageWithoutDuplicates() {
    String firstPageDocument = """
            query {
                bookConnection(first: 2) {
                    edges { cursor node { id } }
                    pageInfo { hasNextPage endCursor }
                }
            }
            """;

    GraphQlTester.Response firstResponse = graphQlTester
            .document(firstPageDocument)
            .execute();

    firstResponse.path("bookConnection.edges[*].node.id")
            .entityList(String.class)
            .containsExactly("5", "4");
    firstResponse.path("bookConnection.pageInfo.hasNextPage")
            .entity(Boolean.class)
            .isEqualTo(true);

    String endCursor = firstResponse.path("bookConnection.pageInfo.endCursor")
            .entity(String.class)
            .get();

    graphQlTester.document("""
            query Next($after: String!) {
                bookConnection(first: 2, after: $after) {
                    edges { node { id } }
                    pageInfo { hasNextPage }
                }
            }
            """)
            .variable("after", endCursor)
            .execute()
            .path("bookConnection.edges[*].node.id")
            .entityList(String.class)
            .containsExactly("3", "2");
}
~~~

Test giả định fixture có ID theo thứ tự `5` đến `1` và service/repository được cấu hình tương ứng. Với test chạy qua database thật, tạo fixture có timestamp trùng nhau để chứng minh tie-breaker ID hoạt động.

## 19. Lỗi thường gặp khi triển khai pagination

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Query vẫn trả toàn bộ collection | Resolver tải hết rồi mới cắt list | Dùng `Pageable`, SQL limit hoặc keyset query tại repository |
| Trang sâu rất chậm | Offset lớn phải bỏ qua nhiều hàng | Chuyển sang cursor/keyset pagination |
| Hai trang có record trùng hoặc bị thiếu | Sort không ổn định hoặc dữ liệu thay đổi giữa hai request | Thêm unique tie-breaker; cân nhắc keyset hoặc snapshot semantics |
| `totalElements` làm query chậm | `Page<T>` thực hiện count query đắt | Dùng `Slice<T>` hoặc connection chỉ có `hasNextPage` |
| Client yêu cầu page size quá lớn | Không có giới hạn server-side | Clamp hoặc reject size vượt ngưỡng tối đa |
| Sort gây lỗi hoặc truy cập field ngoài ý muốn | Dùng raw property string từ client | Dùng enum/allow-list ánh xạ sang property cố định |
| Cursor trang sau bỏ sót record đồng timestamp | Cursor chỉ chứa timestamp | Dùng composite cursor với unique tie-breaker |
| Cursor sửa được bởi client | Base64 bị nhầm là mã hóa | Ký cursor hoặc kiểm tra payload; luôn áp dụng authorization trong query |
| Đổi filter làm trang sau không nhất quán | Cursor không gắn với filter/sort scope | Gắn fingerprint filter/sort vào cursor hoặc giữ variables nhất quán |
| Trang có ít record hơn dự kiến | Filter được áp dụng sau khi lấy page | Đưa filter/tenant vào query trước pagination |
| Trang 20 sách vẫn có nhiều SQL query | N+1 ở field con | Dùng DataLoader hoặc `@BatchMapping` |
| GraphQL không serialize được total count lớn | `Int` vượt giới hạn 32-bit | Dùng custom scalar hoặc bỏ total count |

## 20. Quy trình chọn và triển khai pagination

Khi thiết kế một GraphQL collection field:

1. Xác định UI cần nhảy tới trang bất kỳ hay chỉ tải tiếp dữ liệu.
2. Chọn offset/page-based cho collection vừa phải; chọn cursor/keyset cho collection lớn hoặc thay đổi thường xuyên.
3. Định nghĩa arguments và response shape rõ ràng trong SDL.
4. Đặt default và maximum page size ở server.
5. Chỉ cho phép sort field nằm trong allow-list.
6. Bảo đảm thứ tự có unique tie-breaker.
7. Áp dụng tenant, authorization và filter trước limit/offset.
8. Dùng `Page` khi thật sự cần total count; dùng `Slice` hoặc `first + 1` khi chỉ cần biết còn trang sau.
9. Với cursor, encode đủ các sort keys và ràng buộc cursor với filter/sort scope.
10. Kết hợp DataLoader cho field con để tránh N+1 trong từng trang.
11. Kiểm thử boundary, sort, cursor continuity, missing/invalid cursor và tenant isolation.
12. Đo query count, count-query cost, page depth và response size bằng integration/performance tests.

Pagination hiệu quả cần được thực hiện tại database, có thứ tự ổn định và giới hạn đầu vào rõ ràng. Offset pagination đơn giản cho giao diện cần số trang; cursor/keyset phù hợp hơn cho dữ liệu lớn và luồng tải liên tục. Trong cả hai trường hợp, authorization, filter và DataLoader vẫn là một phần của thiết kế truy vấn.

## Tài liệu tham khảo

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring Data — Paging and Sorting](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html#repositories.special-parameters)
- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [GraphQL Cursor Connections Specification](https://relay.dev/graphql/connections.htm)
