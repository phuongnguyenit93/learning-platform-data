# Cursor pagination

Cursor pagination chia một tập kết quả thành nhiều trang dựa trên vị trí của bản ghi cuối cùng đã đọc. Thay vì yêu cầu server bỏ qua một số lượng dòng bằng offset, client gửi một cursor đại diện cho ranh giới trang trước. Server dùng giá trị đó để tìm các bản ghi tiếp theo theo cùng một thứ tự sắp xếp.

Với GraphQL, cursor pagination thường được biểu diễn theo Relay Connection pattern gồm Connection, Edge, Cursor và PageInfo. Spring for GraphQL cung cấp cơ chế khai báo schema, bind arguments và thực thi resolver; ứng dụng vẫn cần thiết kế cursor, truy vấn keyset, kiểm tra input và xây dựng page metadata. Chỉ thêm argument `first` và `after` vào schema không tự biến truy vấn database thành cursor pagination.

## 1. Vì sao cần cursor pagination?

Offset pagination là cách đơn giản để chia trang:

~~~graphql
query {
    books(page: 4, size: 20) {
        id
        title
    }
}
~~~

Server có thể dịch thành SQL `LIMIT 20 OFFSET 60`. Cách này dễ hiểu và phù hợp với danh sách nhỏ hoặc trang quản trị ít thay đổi. Tuy nhiên, offset lớn có thể khiến database phải đọc và bỏ qua nhiều dòng trước khi trả kết quả.

Offset cũng dễ tạo trải nghiệm không ổn định khi dữ liệu thay đổi giữa các request. Ví dụ trang đầu được đọc, sau đó một bản ghi mới được chèn vào đầu danh sách. Request trang hai vẫn dùng offset cũ có thể lặp lại một bản ghi hoặc bỏ qua một bản ghi.

Cursor pagination dùng một vị trí cụ thể trong thứ tự dữ liệu:

~~~graphql
query {
    books(first: 20, after: "eyJ2IjoxLCJpZCI6...") {
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

Cursor cho biết điểm bắt đầu tiếp theo. Database có thể dùng điều kiện trên các cột sắp xếp để tìm các dòng sau vị trí đó, thay vì bỏ qua một offset lớn.

| Tiêu chí | Offset pagination | Cursor pagination |
| --- | --- | --- |
| Tham số | page/size hoặc offset/limit | first/after hoặc last/before |
| Điều hướng | Nhảy đến trang bất kỳ dễ dàng | Đi tiếp/lùi từ một vị trí |
| Trang sâu | Có thể chậm do offset lớn | Thường ổn định hơn với keyset index |
| Dữ liệu thay đổi | Có thể lặp hoặc bỏ sót dòng giữa các trang | Ít bị dịch chuyển do insert/delete ở trước cursor |
| Tổng số trang | Dễ tính khi có count | Không cần count để lấy trang tiếp |
| Bookmark | Page number dễ lưu | Cursor có thể lưu để tiếp tục từ vị trí |
| Phức tạp triển khai | Thấp | Cao hơn: cursor codec, sort key và page info |

Cursor pagination không tự bảo đảm snapshot nhất quán tuyệt đối. Nếu một bản ghi thay đổi cột sắp xếp giữa hai lần đọc, nó có thể di chuyển qua ranh giới cursor. Muốn kết quả nhất quán theo một snapshot, cần thêm chiến lược snapshot/version hoặc giới hạn dữ liệu theo một mốc thời gian.

## 2. Relay Connection pattern

Relay Connection pattern chuẩn hóa cấu trúc response để client có thể dùng cùng một cách phân trang cho nhiều loại node.

- **Connection:** kết quả phân trang của một collection.
- **Edge:** một phần tử trong connection, gồm node và cursor.
- **Node:** object nghiệp vụ, ví dụ Book.
- **Cursor:** chuỗi đại diện vị trí của edge trong thứ tự kết quả.
- **PageInfo:** metadata về trang hiện tại và khả năng đi tiếp/lùi.

Schema GraphQL minh họa:

~~~graphql
type Query {
    books(
        first: Int
        after: String
        last: Int
        before: String
        filter: BookFilter
    ): BookConnection!
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

input BookFilter {
    keyword: String
    status: BookStatus
}
~~~

`totalCount` là field tùy chọn. Nếu database phải chạy `COUNT(*)` trên tập dữ liệu lớn, field này có thể đắt hơn nhiều so với truy vấn trang. Chỉ thêm khi sản phẩm thật sự cần và có cách tính phù hợp.

Relay convention thường dùng `first/after` cho forward pagination và `last/before` cho backward pagination. Nên định nghĩa rõ contract của API, chẳng hạn không cho phép gửi đồng thời `first` và `last` hoặc đồng thời `after` và `before` trong một request.

## 3. Cursor phải đại diện cho vị trí ổn định

Cursor không nên chỉ là số trang hoặc offset. Nó cần chứa các giá trị đủ để xác định vị trí của một bản ghi trong thứ tự sắp xếp.

Giả sử danh sách sách được sắp xếp theo:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

Cursor có thể chứa:

~~~json
{
  "version": 1,
  "createdAt": "2026-03-10T08:30:00Z",
  "id": "a2d3c2d0-5b0d-4f2c-8a9b-31b10e4c7f20"
}
~~~

Hai giá trị `createdAt` và `id` tạo thành sort key. `id` là tie-breaker duy nhất để hai bản ghi có cùng timestamp vẫn có thứ tự xác định.

Cursor nên được xem là opaque ở phía client. Client nhận cursor từ edge rồi gửi lại nguyên vẹn trong `after` hoặc `before`; client không cần đọc hoặc tự tạo nội dung cursor.

Base64 URL-safe là cách phổ biến để encode payload:

~~~java
String cursor = Base64.getUrlEncoder()
    .withoutPadding()
    .encodeToString(payload.getBytes(StandardCharsets.UTF_8));
~~~

Base64 chỉ encode, không mã hóa và không chống sửa đổi. Nếu cursor chứa thông tin nhạy cảm hoặc client không được phép thay đổi sort key, có thể ký payload bằng HMAC hoặc dùng token có chữ ký. Không đưa secret, thông tin xác thực hay dữ liệu cá nhân không cần thiết vào cursor.

## 4. Thiết kế sort key có thứ tự toàn phần

Một cursor chỉ hoạt động chính xác khi sort order ổn định. Không nên chỉ sắp xếp theo `createdAt` nếu nhiều bản ghi có cùng timestamp:

~~~sql
ORDER BY created_at DESC
~~~

Nếu hai hàng có cùng `created_at`, database không bắt buộc giữ một thứ tự nhất quán giữa các lần query. Khi cursor cắt giữa nhóm có timestamp giống nhau, một bản ghi có thể bị lặp hoặc bỏ qua.

Thêm một cột unique làm tie-breaker:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

Sort key phải có thứ tự xác định, đủ duy nhất khi kết hợp các cột, có biểu diễn chính xác trong cursor, dùng cùng quy tắc so sánh ở codec và database, và được hỗ trợ bởi index phù hợp. Nếu sort field có thể null, phải định nghĩa nulls first/last và đưa trạng thái null vào predicate/cursor, hoặc chọn sort key không nullable.

## 5. Keyset predicate cho forward pagination

Với thứ tự giảm dần:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

Để lấy các bản ghi sau cursor gồm createdAt và id, điều kiện là:

~~~sql
WHERE
    created_at < :cursorCreatedAt
    OR (
        created_at = :cursorCreatedAt
        AND id < :cursorId
    )
ORDER BY created_at DESC, id DESC
LIMIT :limit
~~~

Điều kiện này tương đương so sánh tuple ở database hỗ trợ tuple comparison. Biểu thức tường minh thường dễ chuyển sang nhiều dialect hơn. Nếu sort tăng dần, dấu so sánh và thứ tự cần đổi tương ứng. Không giữ predicate nhỏ hơn khi đổi ORDER BY sang ASC.

Filter phải được áp dụng cùng truy vấn:

~~~sql
SELECT id, title, status, created_at
FROM book
WHERE tenant_id = :tenantId
  AND status = :status
  AND (
      created_at < :cursorCreatedAt
      OR (created_at = :cursorCreatedAt AND id < :cursorId)
  )
ORDER BY created_at DESC, id DESC
LIMIT :limit
~~~

Trong thực tế, phần cursor predicate chỉ được thêm khi có cursor. Filter và authorization scope phải luôn được áp dụng trước khi giới hạn trang.

## 6. Lấy n + 1 bản ghi để tính hasNextPage

Nếu client yêu cầu `first = 20`, server lấy tối đa 21 bản ghi:

1. Query với `LIMIT first + 1`.
2. Nếu có 21 bản ghi, tồn tại ít nhất một bản ghi tiếp theo.
3. Đặt `hasNextPage = true`.
4. Bỏ bản ghi thứ 21 khỏi danh sách trả về.
5. Tạo edge/cursor cho 20 bản ghi còn lại.

Ví dụ:

~~~java
int requestedSize = 20;
List<Book> rows = repository.findAfter(cursor, requestedSize + 1);

boolean hasNextPage = rows.size() > requestedSize;
if (hasNextPage) {
    rows = new ArrayList<>(rows.subList(0, requestedSize));
}
~~~

Kỹ thuật này tránh phải chạy truy vấn COUNT(*) chỉ để biết có trang tiếp theo hay không.

Với forward pagination, `hasPreviousPage` có thể cần truy vấn EXISTS để kiểm tra còn bản ghi trước vị trí đầu tiên hay không. Không suy ra giá trị này chỉ từ việc client đã gửi `after`; nếu API dùng semantics best-effort, cần công bố rõ.

## 7. Backward pagination với last và before

Backward pagination cho phép client lấy các bản ghi đứng trước cursor. Với sort order công khai là DESC, query có thể đổi sang ASC để lấy các bản ghi gần cursor nhất:

~~~sql
SELECT id, title, created_at
FROM book
WHERE
    created_at > :cursorCreatedAt
    OR (
        created_at = :cursorCreatedAt
        AND id > :cursorId
    )
ORDER BY created_at ASC, id ASC
LIMIT :limit
~~~

Nếu client yêu cầu `last = 20`, server lấy 21 dòng theo chiều ngược, bỏ dòng dư, đảo danh sách còn lại về thứ tự DESC của connection rồi tạo edges và PageInfo. Không trả list theo thứ tự ASC chỉ vì query nội bộ dùng ASC.

Backward pagination có thể cần một truy vấn EXISTS khác để tính hasNextPage. Hãy test rõ các cờ PageInfo cho trang đầu, trang giữa, trang cuối và trường hợp không có dữ liệu.

## 8. Validate pagination arguments

Server nên kiểm tra arguments trước khi gọi repository:

- `first` và `last` không âm.
- Có giới hạn tối đa, ví dụ 100 edges mỗi request.
- Không nhận `first` cùng `last` nếu API không hỗ trợ kết hợp.
- Không nhận `after` và `before` cùng lúc nếu contract không cho phép.
- Cursor phải decode được và đúng version.
- Cursor phải chứa đủ sort key và kiểu dữ liệu hợp lệ.
- Filter/sort phải nằm trong allowlist của API.

Ví dụ:

~~~java
private int validatePageSize(Integer requested) {
    int size = requested == null ? 20 : requested;

    if (size < 0) {
        throw new InvalidPaginationException("Page size must not be negative");
    }
    if (size > 100) {
        throw new InvalidPaginationException("Page size exceeds the limit");
    }
    return size;
}
~~~

Có thể cho phép `first = 0` để client chỉ hỏi PageInfo, nhưng cần định nghĩa rõ cách tính hasNextPage và endCursor. Một số API chọn yêu cầu page size lớn hơn 0 để đơn giản hóa. Điều quan trọng là contract nhất quán và được test.

Cursor sai định dạng nên được ánh xạ thành lỗi request rõ ràng, ví dụ BAD_REQUEST, không để lỗi parse Base64 hoặc UUID biến thành INTERNAL_ERROR.

## 9. Tạo cursor codec

Một codec đơn giản có thể encode version, timestamp và ID. Ví dụ sau dùng payload văn bản phân tách bằng dấu hai chấm; các thành phần được chọn sao cho không chứa dấu phân tách:

~~~java
public record BookCursor(Instant createdAt, UUID id) {
}

public class BookCursorCodec {

    private static final String VERSION = "v1";

    public String encode(BookCursor cursor) {
        String value = VERSION + ":"
            + cursor.createdAt().toEpochMilli() + ":"
            + cursor.id();

        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(value.getBytes(StandardCharsets.UTF_8));
    }

    public BookCursor decode(String encoded) {
        try {
            String value = new String(
                Base64.getUrlDecoder().decode(encoded),
                StandardCharsets.UTF_8);

            String[] parts = value.split(":", -1);
            if (parts.length != 3 || !VERSION.equals(parts[0])) {
                throw new InvalidPaginationException("Invalid cursor");
            }

            Instant createdAt =
                Instant.ofEpochMilli(Long.parseLong(parts[1]));
            UUID id = UUID.fromString(parts[2]);

            return new BookCursor(createdAt, id);
        }
        catch (IllegalArgumentException ex) {
            throw new InvalidPaginationException("Invalid cursor", ex);
        }
    }
}
~~~

Codec này chỉ minh họa format tối thiểu. Production cần quyết định cách xử lý version cũ, precision timestamp, chữ ký chống tampering và cursor có còn hợp lệ sau khi sort/filter thay đổi hay không.

Không dùng toString() tùy tiện cho sort key nếu format không ổn định. Timestamp cần giữ đúng precision mà database dùng để so sánh; nếu database lưu microseconds nhưng cursor chỉ giữ milliseconds, nhiều bản ghi có thể bị gộp sai ranh giới.

## 10. Xây dựng Connection và Edge trong Java

Có thể dùng record làm response model:

~~~java
public record BookEdge(String cursor, Book node) {
}

public record PageInfo(
        boolean hasNextPage,
        boolean hasPreviousPage,
        String startCursor,
        String endCursor) {
}

public record BookConnection(
        List<BookEdge> edges,
        PageInfo pageInfo,
        Long totalCount) {
}
~~~

Service chuyển danh sách đã phân trang thành edges:

~~~java
private BookConnection toConnection(
        List<Book> books,
        boolean hasNextPage,
        boolean hasPreviousPage) {

    List<BookEdge> edges = books.stream()
        .map(book -> new BookEdge(
            cursorCodec.encode(new BookCursor(
                book.createdAt(), book.id())),
            book))
        .toList();

    String startCursor = edges.isEmpty()
        ? null
        : edges.get(0).cursor();
    String endCursor = edges.isEmpty()
        ? null
        : edges.get(edges.size() - 1).cursor();

    PageInfo pageInfo = new PageInfo(
        hasNextPage,
        hasPreviousPage,
        startCursor,
        endCursor);

    return new BookConnection(edges, pageInfo, null);
}
~~~

Với connection rỗng, startCursor và endCursor nên là null. Không tự tạo cursor giả cho trang không có edge.

## 11. Resolver trong Spring for GraphQL

Spring for GraphQL bind arguments bằng `@Argument`. Resolver nên giữ mỏng và chuyển việc validate/query/build connection sang service:

~~~java
@Controller
public class BookQueryController {

    private final BookConnectionService connectionService;

    public BookQueryController(BookConnectionService connectionService) {
        this.connectionService = connectionService;
    }

    @QueryMapping
    public BookConnection books(
            @Argument Integer first,
            @Argument String after,
            @Argument BookFilter filter) {

        return connectionService.findBooks(first, after, filter);
    }
}
~~~

Ví dụ trên thể hiện forward pagination. Nếu hỗ trợ backward pagination, thêm last và before rồi validate các cặp argument theo contract. Không nên đặt toàn bộ SQL, cursor parsing và PageInfo calculation trực tiếp trong controller.

## 12. Repository keyset query

Repository cần thực hiện predicate dựa trên sort key. Với Spring Data JPA, có thể dùng custom repository để kiểm soát query:

~~~java
public interface BookRepositoryCustom {

    List<Book> findAfter(
        UUID tenantId,
        BookStatus status,
        BookCursor cursor,
        int limit);
}
~~~

Một triển khai dùng JPQL hoặc Criteria API cần diễn đạt điều kiện:

~~~sql
createdAt < :createdAt
OR (createdAt = :createdAt AND id < :id)
~~~

Nếu cursor null, bỏ phần predicate cursor và lấy từ đầu connection. Query phải áp dụng tenant và filter trong cùng câu truy vấn:

~~~sql
WHERE tenant_id = :tenantId
  AND status = :status
  AND (
      :hasCursor = false
      OR created_at < :createdAt
      OR (created_at = :createdAt AND id < :cursorId)
  )
ORDER BY created_at DESC, id DESC
LIMIT :limit
~~~

Đây là SQL minh họa; cách bind optional predicate và limit phụ thuộc database/ORM. Với JPA, có thể dùng native query, Criteria API hoặc custom repository để tạo điều kiện động.

Spring Data có hỗ trợ scrolling với ScrollPosition, Window<T> và keyset-based scrolling trong các phiên bản phù hợp. Nếu dùng cơ chế này, cần xác nhận repository method, sort và property projection đáp ứng yêu cầu keyset. Window<T> của Spring Data là abstraction scrolling; ứng dụng vẫn cần chuyển kết quả sang GraphQL Connection/Edge/PageInfo theo schema public.

## 13. Index cho keyset pagination

Query có thể dùng keyset predicate nhưng vẫn chậm nếu index không phù hợp. Với truy vấn theo tenant, status và thứ tự created_at DESC, id DESC, một index có thể bắt đầu bằng các cột equality filter rồi đến sort key:

~~~sql
CREATE INDEX idx_book_tenant_status_created_id
ON book (tenant_id, status, created_at DESC, id DESC);
~~~

Index chính xác phụ thuộc database, độ chọn lọc của filter, số lượng status và workload thực tế. Không tạo index theo mọi tổ hợp filter một cách tùy tiện; hãy xem execution plan và đo trên dữ liệu gần với production.

- Filter equality thường đứng trước sort key trong composite index.
- Các cột cursor cần nằm trong index theo đúng thứ tự sort.
- Nếu filter tùy chọn, một index duy nhất có thể không tối ưu cho mọi query shape.
- Projection chỉ lấy các cột cần thiết có thể giảm I/O.
- Sort direction và null ordering cần khớp predicate.

Dùng EXPLAIN hoặc EXPLAIN ANALYZE theo database để xác nhận query thực sự dùng index và không quét một tập dữ liệu lớn.

## 14. Filter, sort và cursor phải nhất quán

Cursor được tạo theo một thứ tự cụ thể. Nếu client dùng cursor từ query status=PUBLISHED rồi gửi sang query status=DRAFT, ranh giới có thể không còn ý nghĩa với tập dữ liệu mới.

Có hai cách xử lý:

1. Chấp nhận cursor chỉ là sort key, áp dụng nó cho filter mới theo semantics đã công bố.
2. Đưa fingerprint của filter và sort vào cursor, từ chối cursor khi query scope thay đổi.

Fingerprint nên được tính từ biểu diễn canonical của các filter/sort được hỗ trợ. Không serialize Map không ổn định rồi hash trực tiếp nếu thứ tự key có thể thay đổi.

Sort field do client chọn phải nằm trong allowlist. Không nối tên cột tùy ý từ GraphQL argument vào SQL. Mỗi sort option cần định nghĩa predicate, tie-breaker và index phù hợp.

## 15. Authorization và tenant scope

Cursor không phải credential và không cấp quyền truy cập. Người dùng có thể gửi cursor lấy từ request khác, vì vậy mọi trang đều phải áp dụng authorization theo principal hiện tại.

Ví dụ:

~~~java
public BookConnection findBooks(
        String username,
        Integer first,
        String after,
        BookFilter filter) {

    UUID tenantId = tenantAuthorization.requireCurrentTenant(username);
    int size = validatePageSize(first);
    BookCursor cursor = after == null ? null : cursorCodec.decode(after);

    List<Book> rows = repository.findAfter(
        tenantId, filter.status(), cursor, size + 1);

    return buildConnection(rows, size);
}
~~~

tenantId phải được suy ra từ principal hoặc xác minh membership ở server. Không dùng tenant ID chỉ vì nó được decode từ cursor hoặc gửi trong GraphQL argument.

Nếu cursor có chữ ký, chữ ký chỉ giúp phát hiện cursor bị sửa. Nó không thay thế authorization, vì người dùng vẫn có thể replay một cursor hợp lệ trong một context không còn quyền.

## 16. Dữ liệu thay đổi giữa các trang

Cursor pagination giảm ảnh hưởng của insert/delete ở trước cursor, nhưng không tạo snapshot tự động.

Ví dụ sort DESC theo created_at:

- Một bản ghi mới được insert ở đầu danh sách sau khi client đọc trang đầu: trang tiếp theo dùng cursor cũ vẫn tiếp tục từ ranh giới trước đó, nên bản ghi mới thường không làm dịch chuyển các dòng đã đọc.
- Một bản ghi ở phía sau cursor bị xóa: trang tiếp theo đơn giản không còn trả bản ghi đó.
- Một bản ghi đã đọc được cập nhật created_at và chuyển xuống sau cursor: client có thể gặp lại bản ghi.
- Một bản ghi chưa đọc được cập nhật sort key và chuyển lên trước cursor: client có thể không nhìn thấy nó trong lượt duyệt hiện tại.

Để giảm dịch chuyển, ưu tiên sort key bất biến như createdAt và unique ID. Nếu cần duyệt một tập snapshot chính xác, cursor có thể chứa snapshot timestamp/version hoặc query dùng watermark cố định, ví dụ chỉ đọc dữ liệu có created_at nhỏ hơn hoặc bằng snapshotTime.

Snapshot semantics làm tăng độ phức tạp và có thể cần giữ version hoặc transaction snapshot qua nhiều request. Chỉ triển khai khi yêu cầu nghiệp vụ cần; không giả định cursor tự cung cấp snapshot isolation.

## 17. PageInfo và edge cases

PageInfo cần được kiểm tra cho các tình huống:

| Tình huống | edges | hasNextPage | hasPreviousPage |
| --- | --- | --- | --- |
| Không có dữ liệu | Rỗng | false | false |
| Trang đầu có trang sau | Có dữ liệu | true | false |
| Trang giữa | Có dữ liệu | true/false theo dữ liệu còn lại | true |
| Trang cuối | Có dữ liệu | false | true |
| Cursor ở cuối tập | Rỗng hoặc trang rỗng theo contract | false | true nếu có dữ liệu trước |
| Page size bằng 0 | Rỗng | Theo query existence và contract | Theo query existence và contract |

Không đặt hasNextPage = edges.size() == first vì số lượng bằng page size không chứng minh có bản ghi tiếp theo. Cần lấy first + 1 hoặc chạy truy vấn EXISTS.

Với hasPreviousPage, đừng mặc định true chỉ vì có after. Nếu cần giá trị chính xác, kiểm tra tồn tại bản ghi trước vị trí bắt đầu theo cùng filter, tenant và sort order.

## 18. totalCount có nên đưa vào Connection?

totalCount tiện cho UI hiển thị "có 1.234 kết quả", nhưng count có thể tốn chi phí:

- Filter phức tạp có thể yêu cầu scan nhiều index entry.
- Join và authorization predicate có thể làm count đắt hơn query trang.
- Dữ liệu thay đổi giữa query count và query edges khiến hai giá trị không cùng snapshot.

Các lựa chọn:

- Không cung cấp totalCount nếu UI không cần.
- Tính count riêng và cache trong thời gian ngắn.
- Dùng approximate count nếu sản phẩm chấp nhận.
- Chỉ cung cấp count cho một số filter có index tốt.

Không chạy count chỉ để biết có trang tiếp theo; n + 1 thường rẻ hơn.

## 19. Tránh N+1 khi resolve node fields

Cursor pagination chỉ tối ưu việc lấy danh sách node. Nếu mỗi edge node có nested field như author, category hoặc reviews, resolver vẫn có thể tạo N+1 query.

Ví dụ query:

~~~graphql
query {
    books(first: 20) {
        edges {
            node {
                id
                title
                author {
                    id
                    name
                }
            }
        }
    }
}
~~~

Hãy dùng DataLoader hoặc @BatchMapping cho nested association để gom các key. Batch loader cần áp dụng cùng tenant/authorization scope và không chia sẻ cache giữa các principal.

Pagination query cũng nên chỉ lấy các cột cần cho connection và cursor. Nếu resolver cần nested data, để DataLoader xử lý theo batch thay vì join tất cả collection có thể nhân bản row và làm sai page boundary.

## 20. Kiểm thử cursor pagination bằng GraphQlTester

Test nên thực thi GraphQL document thật để xác nhận schema, resolver, cursor và PageInfo cùng hoạt động:

~~~java
@Test
void returnsNextPageAfterEndCursor() {
    var firstPage = graphQlTester.document("""
            query {
                books(first: 2) {
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
            """)
        .execute();

    firstPage.errors().verify();
    firstPage.path("books.edges")
        .entityList(BookEdgeView.class)
        .hasSize(2);
    firstPage.path("books.pageInfo.hasNextPage")
        .entity(Boolean.class)
        .isEqualTo(true);

    String endCursor = firstPage.path("books.pageInfo.endCursor")
        .entity(String.class)
        .get();

    var secondPage = graphQlTester.document("""
            query NextBooks($after: String) {
                books(first: 2, after: $after) {
                    edges {
                        node {
                            id
                        }
                    }
                    pageInfo {
                        hasNextPage
                    }
                }
            }
            """)
        .variable("after", endCursor)
        .execute();

    secondPage.errors().verify();
    secondPage.path("books.edges")
        .entityList(BookEdgeIdView.class)
        .hasSize(2);
}
~~~

Fixture cần có ít nhất ba hoặc bốn bản ghi theo thứ tự đã biết để test trang đầu và trang tiếp theo. DTO test BookEdgeView và BookEdgeIdView cần khớp đúng response selection.

## 21. Các trường hợp kiểm thử quan trọng

Nên bao phủ:

1. Trang đầu không có cursor.
2. Trang tiếp theo dùng endCursor của trang trước.
3. Trang cuối có hasNextPage = false.
4. Connection rỗng có cursor null.
5. Nhiều bản ghi có cùng sort timestamp vẫn không lặp hoặc bỏ sót nhờ tie-breaker.
6. Cursor sai Base64, sai version, thiếu field hoặc UUID không hợp lệ bị từ chối như bad request.
7. Page size âm hoặc vượt giới hạn bị từ chối.
8. Filter khác nhau có semantics cursor rõ ràng.
9. Tenant A không dùng cursor để đọc dữ liệu tenant B.
10. Backward pagination trả edge đúng thứ tự công khai.
11. Insert/delete giữa hai trang không làm lặp bản ghi đã đọc trong kịch bản được hỗ trợ.
12. Mutation của sort key có hành vi đã được định nghĩa.
13. DataLoader nested field không tạo N+1.
14. totalCount đúng nếu API công bố field này.

Test keyset query ở repository layer với dữ liệu có timestamp trùng nhau. Test GraphQL layer kiểm tra response contract. Integration test với database thật cần xác nhận SQL dialect, sort, index và query plan khi hiệu năng là mục tiêu.

## 22. Những lỗi thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Cursor chỉ chứa offset | Hiệu năng và độ ổn định không khác offset pagination | Encode sort key của bản ghi |
| Sort không có unique tie-breaker | Lặp hoặc bỏ sót dòng khi sort key trùng | Thêm ID hoặc unique key vào sort |
| Predicate không khớp ORDER BY | Trang tiếp theo sai thứ tự hoặc mất dòng | Thiết kế predicate theo từng sort direction |
| Không lấy n + 1 | hasNextPage không chính xác | Fetch thêm một row hoặc dùng EXISTS |
| Luôn chạy COUNT(*) | Tăng chi phí cho mỗi trang | Chỉ cung cấp totalCount khi cần |
| Cursor không version | Không thể thay đổi format an toàn | Thêm version và xử lý cursor cũ |
| Xem Base64 là bảo mật | Client có thể decode/sửa cursor | Dùng HMAC nếu cần chống tampering |
| Tin cursor để cấp quyền | Replay cursor có thể vượt scope | Kiểm tra authorization trên mọi request |
| Filter thay đổi nhưng cursor không có policy | Ranh giới trang khó dự đoán | Ràng buộc cursor với filter/sort hoặc công bố semantics |
| Không có index phù hợp | Keyset query vẫn chậm | Đo execution plan và tạo composite index |
| Nested resolver query từng node | N+1 vẫn tồn tại | Dùng DataLoader hoặc @BatchMapping |
| Không đặt giới hạn page size | Client có thể yêu cầu tập quá lớn | Validate và cap page size |

## 23. Nguyên tắc thiết kế cursor pagination

Thiết kế schema theo Connection/Edge/PageInfo để client có contract nhất quán. Cursor phải opaque, có version và chứa đầy đủ sort key của một thứ tự ổn định; luôn thêm unique tie-breaker. Với forward pagination, dùng keyset predicate và lấy first + 1 để xác định trang tiếp theo. Với backward pagination, query theo chiều ngược rồi đảo kết quả về connection order.

Áp dụng filter và authorization scope trong cùng database query. Giới hạn page size, validate cursor, không xem cursor là credential và chỉ ký payload khi cần chống tampering. Tạo index khớp filter và sort, đo execution plan, tránh count không cần thiết và dùng DataLoader cho nested fields.

Kiểm thử trang đầu, trang tiếp theo, trang cuối, cursor sai, sort key trùng, dữ liệu thay đổi, backward pagination, tenant isolation và N+1. Cursor pagination giúp duyệt dữ liệu lớn ổn định hơn khi được kết hợp với keyset query và sort/index phù hợp; bản thân chuỗi cursor trong GraphQL schema không tạo ra lợi ích hiệu năng nếu repository vẫn dùng offset.

## Tài liệu tham khảo

- [Relay Cursor Connections Specification](https://relay.dev/graphql/connections.htm)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring Data Commons — Scrolling](https://docs.spring.io/spring-data/commons/reference/repositories/scrolling.html)
- [Spring Data JPA — Query Methods and Scrolling](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
