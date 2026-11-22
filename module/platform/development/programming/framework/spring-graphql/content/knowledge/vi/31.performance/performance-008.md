# Offset pagination

Khi một GraphQL query trả về một tập dữ liệu lớn, server không nên tải toàn bộ bản ghi rồi gửi về client trong một response. Offset pagination chia tập kết quả thành các lát nhỏ: client gửi vị trí bắt đầu bằng `offset` và số phần tử tối đa muốn nhận bằng `limit`. Database bỏ qua một số hàng đầu tiên rồi trả về phần tiếp theo.

Spring for GraphQL cho phép xây dựng offset pagination trực tiếp trong SDL và annotated controller bằng `@QueryMapping`, `@Argument`. Nếu dùng Spring Data Querydsl hoặc Query by Example, có thể tận dụng `@GraphQlRepository` để tự đăng ký các query paginated; chế độ auto-registration này dùng offset-based pagination với mặc định 20 phần tử mỗi trang.

Bài học này đi từ hợp đồng GraphQL, cách triển khai resolver và repository, đến thứ tự sắp xếp ổn định, giới hạn đầu vào, chiến lược tính tổng số bản ghi, hiệu năng ở offset lớn, tính nhất quán khi dữ liệu thay đổi và kiểm thử.

## 1. Offset pagination là gì?

Offset pagination xác định một trang bằng hai giá trị:

- `offset`: số bản ghi bỏ qua tính từ đầu tập kết quả.
- `limit`: số bản ghi tối đa được trả về.

Ví dụ với `limit = 20`:

| Trang | Offset | Limit | Vị trí bản ghi |
| --- | ---: | ---: | --- |
| 1 | 0 | 20 | 1–20 |
| 2 | 20 | 20 | 21–40 |
| 3 | 40 | 20 | 41–60 |
| 4 | 60 | 20 | 61–80 |

Offset thường bắt đầu từ 0. Nếu client gửi `offset = 40` và `limit = 20`, server bỏ qua 40 bản ghi đầu rồi lấy tối đa 20 bản ghi tiếp theo.

Trong SQL, ý tưởng thường được biểu diễn bằng:

```sql
SELECT id, title, created_at
FROM books
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 40;
```

Tên cú pháp có thể khác theo hệ quản trị cơ sở dữ liệu. Trong JPA, có thể dùng `Query.setFirstResult(offset)` và `Query.setMaxResults(limit)` để yêu cầu provider áp dụng giới hạn và offset phù hợp với dialect.

Offset pagination dễ hiểu và thuận tiện cho giao diện có số trang, nút Next/Previous hoặc cho phép nhảy đến một vị trí cụ thể. Tuy nhiên, offset lớn có thể tốn tài nguyên và dữ liệu thay đổi giữa hai request có thể làm vị trí trang bị dịch chuyển.

## 2. Thiết kế GraphQL schema cho offset và limit

Một schema đơn giản cho API thư viện:

```graphql
type Query {
  books(offset: Int = 0, limit: Int = 20): BookPage!
}

type BookPage {
  items: [Book!]!
  offset: Int!
  limit: Int!
  hasNextPage: Boolean!
}

type Book {
  id: ID!
  title: String!
  createdAt: String!
}
```

`books` trả về một object `BookPage` thay vì chỉ trả về list. Response có thể mang theo metadata để client biết vị trí hiện tại và còn dữ liệu tiếp theo hay không.

Ví dụ client yêu cầu trang đầu:

```graphql
query FirstBooks {
  books(offset: 0, limit: 20) {
    offset
    limit
    hasNextPage
    items {
      id
      title
      createdAt
    }
  }
}
```

Request trang tiếp theo:

```graphql
query NextBooks($offset: Int!, $limit: Int!) {
  books(offset: $offset, limit: $limit) {
    offset
    limit
    hasNextPage
    items {
      id
      title
    }
  }
}
```

Variables:

```json
{
  "offset": 20,
  "limit": 20
}
```

Response mẫu:

```json
{
  "data": {
    "books": {
      "offset": 20,
      "limit": 20,
      "hasNextPage": true,
      "items": [
        {
          "id": "book-21",
          "title": "Spring GraphQL",
          "createdAt": "2026-10-15T08:30:00Z"
        }
      ]
    }
  }
}
```

Trong ví dụ, danh sách rút gọn để dễ đọc. Thực tế có thể trả tối đa 20 item.

### Vì sao trả về BookPage?

Nếu schema chỉ trả `[Book!]!`, client không biết server đã áp dụng offset/limit nào và không biết còn trang sau hay không. Một page object có thể mở rộng thêm:

- `totalCount` nếu UI cần hiển thị tổng số bản ghi hoặc số trang.
- `hasPreviousPage` nếu client cần trạng thái trang trước.
- `nextOffset` nếu muốn server trả trực tiếp offset kế tiếp.
- `appliedFilters` nếu cần xác nhận filter đã áp dụng.

Không nên thêm metadata không được client sử dụng. Mỗi field bổ sung có thể kéo theo truy vấn database hoặc logic tính toán khác.

### Chú ý về GraphQL Int

GraphQL built-in scalar `Int` là số nguyên có dấu 32-bit. Vì vậy, `offset` và `limit` dùng `Int` không thể biểu diễn số nguyên tùy ý lớn hơn giới hạn 32-bit. Với dữ liệu rất lớn, hãy đặt giới hạn offset phù hợp hoặc định nghĩa custom scalar/chuỗi cho kiểu số rộng hơn nếu hợp đồng API thực sự cần. `totalCount` cũng có giới hạn tương tự nếu khai báo là `Int`.

## 3. Nhận offset và limit bằng @QueryMapping

Spring for GraphQL dùng `@QueryMapping` để ánh xạ method trong controller vào field thuộc GraphQL `Query`. Annotation `@Argument` bind các đối số GraphQL vào tham số Java.

```java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public BookPage books(
            @Argument int offset,
            @Argument int limit) {

        return bookService.findBooks(offset, limit);
    }
}
```

Vì schema đã khai báo default value, nếu client bỏ qua hai argument thì GraphQL sẽ dùng giá trị mặc định trước khi gọi resolver. Nếu muốn tự áp dụng default trong Java thay vì SDL, có thể khai báo argument nullable bằng wrapper type và tự xử lý giá trị null.

Đừng mặc định rằng `Pageable` sẽ tự động được bind từ hai argument `offset` và `limit` trong mọi phiên bản Spring for GraphQL. Controller support pagination chuyên biệt có thể dùng `Subrange` hoặc `ScrollSubrange` khi đã cấu hình `CursorStrategy`; đây là một cơ chế khác. Với hợp đồng offset/limit tự định nghĩa, bind rõ các scalar bằng `@Argument` là cách trực tiếp.

## 4. Validate offset và limit

Offset âm hoặc limit quá lớn có thể tạo request không hợp lệ hoặc khiến server phải xử lý lượng dữ liệu không cần thiết. Cần kiểm tra ở server, ngay cả khi client đã validate.

Ví dụ giới hạn tối đa 100 bản ghi:

```java
public BookPage findBooks(int offset, int limit) {
    if (offset < 0) {
        throw new IllegalArgumentException("offset must be greater than or equal to zero");
    }
    if (limit < 1 || limit > 100) {
        throw new IllegalArgumentException("limit must be between 1 and 100");
    }

    // Fetch page after validating arguments.
}
```

Trong ứng dụng production, nên chuyển lỗi input này thành GraphQL error có phân loại phù hợp như `BAD_REQUEST` bằng `@GraphQlExceptionHandler` hoặc `DataFetcherExceptionResolver`. Không để lỗi input không hợp lệ bị hiển thị như lỗi hệ thống nội bộ.

Các quy tắc thường dùng:

| Input | Quy tắc |
| --- | --- |
| offset | Không âm |
| limit | Lớn hơn 0 |
| limit tối đa | Giới hạn theo tải database và kích thước response |
| offset quá lớn | Có thể từ chối, giới hạn hoặc chuyển client sang cơ chế tìm kiếm khác |
| offset + limit | Tính toán an toàn, tránh overflow khi dùng số nguyên |

Nếu cần Bean Validation, có thể đóng gói tham số vào input object và dùng constraint phù hợp. Với hai scalar argument riêng lẻ, validate tường minh trong service cũng là một lựa chọn rõ ràng.

Đừng chỉ clamp giá trị limit lớn về 100 mà không thông báo. Client cần biết giá trị được chấp nhận; trả lỗi validation rõ ràng giúp tránh việc UI hiểu sai số item đã nhận.

## 5. Query dữ liệu bằng JPA offset

JPA hỗ trợ offset và giới hạn kết quả qua `setFirstResult` và `setMaxResults`. Ví dụ repository:

```java
@Repository
public class JpaBookPageRepository {

    @PersistenceContext
    private EntityManager entityManager;

    public List<Book> findSlice(int offset, int limit) {
        return entityManager.createQuery("""
                select book
                from Book book
                order by book.createdAt desc, book.id desc
                """, Book.class)
                .setFirstResult(offset)
                .setMaxResults(limit)
                .getResultList();
    }
}
```

Trong truy vấn, `ORDER BY` có hai tiêu chí:

1. `createdAt DESC` để sách mới xuất hiện trước.
2. `id DESC` để phá hòa khi nhiều sách có cùng thời điểm tạo.

Tiêu chí thứ hai rất quan trọng. Nếu chỉ sắp xếp theo một cột không duy nhất, database có thể trả các bản ghi cùng giá trị theo thứ tự khác nhau giữa các lần chạy. Khi client yêu cầu trang kế tiếp, một số bản ghi có thể bị lặp hoặc bị bỏ qua ngay cả khi dữ liệu không đổi.

### Dùng limit + 1 để biết còn trang sau

Nếu schema chỉ cần `hasNextPage` mà không cần tổng số bản ghi, không nhất thiết chạy thêm count query. Hãy lấy nhiều hơn limit một hàng:

```java
public BookPage findBooks(int offset, int limit) {
    validate(offset, limit);

    List<Book> rows = repository.findSlice(offset, limit + 1);
    boolean hasNextPage = rows.size() > limit;

    List<Book> items = hasNextPage
            ? rows.subList(0, limit)
            : rows;

    return new BookPage(
            List.copyOf(items),
            offset,
            limit,
            hasNextPage);
}
```

DTO:

```java
public record BookPage(
        List<Book> items,
        int offset,
        int limit,
        boolean hasNextPage) {
}
```

Vì limit đã được giới hạn tối đa 100, phép tính `limit + 1` không thể tràn số. Item thứ limit + 1 chỉ dùng để xác định còn dữ liệu; không đưa item đó vào response.

Phương pháp này gần với khái niệm `Slice` trong Spring Data: biết có phần tiếp theo mà không phải tính tổng toàn bộ kết quả.

## 6. Khi nào cần totalCount?

Một số giao diện cần tổng số bản ghi để hiển thị “1–20 trong 1.250 kết quả” hoặc tính số trang. Khi đó, có thể bổ sung field `totalCount` và chạy count query.

Ví dụ:

```java
public long countBooks() {
    return entityManager.createQuery(
            "select count(book) from Book book",
            Long.class)
            .getSingleResult();
}
```

Nếu query có filter, count query phải áp dụng cùng predicate với truy vấn lấy page:

```sql
SELECT COUNT(*)
FROM books
WHERE status = 'PUBLISHED';
```

Truy vấn dữ liệu cũng phải dùng đúng filter `status = 'PUBLISHED'`. Nếu hai query khác điều kiện, `totalCount` sẽ không khớp với tập dữ liệu mà client đang phân trang.

### Page và Slice

| Kết quả | Dữ liệu cần lấy | Chi phí bổ sung |
| --- | --- | --- |
| Slice | limit + 1 item | Không cần count toàn bộ |
| Page có totalCount | limit item + count query | Thêm một truy vấn đếm |

Count query có thể tốn kém với join phức tạp, filter nhiều điều kiện hoặc bảng lớn. Chỉ trả `totalCount` khi UI hoặc nghiệp vụ thực sự cần.

GraphQL built-in `Int` chỉ chứa số nguyên 32-bit. Nếu tổng số bản ghi có thể vượt giới hạn này, dùng custom scalar phù hợp hoặc biểu diễn total count dưới dạng chuỗi theo hợp đồng API; không ép `long` sang `int` một cách âm thầm.

## 7. Offset pagination với Spring Data @GraphQlRepository

Nếu ứng dụng đã dùng Spring Data Querydsl hoặc Query by Example, Spring for GraphQL có thể tự đăng ký DataFetcher cho repository được đánh dấu `@GraphQlRepository`. Tính năng auto-registration hỗ trợ query một bản ghi, nhiều bản ghi và paginated query.

Ví dụ repository dùng Querydsl:

```java
@GraphQlRepository
public interface BookRepository extends
        JpaRepository<Book, Long>,
        QuerydslPredicateExecutor<Book> {
}
```

Schema khai báo connection type có tên dựa trên domain type:

```graphql
type Query {
  books: BooksConnection
}

type Book {
  id: ID!
  title: String!
}
```

Với paginated query, tên connection type phải khớp tên domain type ở phần trước hậu tố `Connection`. Ví dụ domain type `Book` tương ứng `BooksConnection`. Spring for GraphQL Boot Starter tự phát hiện repository được đánh dấu và đăng ký runtime wiring tương ứng nếu có integration cần thiết trên classpath.

Trong auto-registration, pagination dùng offset-based với mặc định 20 item mỗi trang. Đây là cách nhanh để expose một repository query đơn giản. Nếu cần hợp đồng riêng có `offset`, `limit`, metadata tùy chỉnh, filter đặc thù hoặc giới hạn truy cập riêng, hãy tạo controller và DataFetcher chủ động thay vì phụ thuộc vào convention mặc định.

### QuerydslDataFetcher và Query by Example

Spring for GraphQL có hai integration chính:

| Integration | Repository interface | Builder |
| --- | --- | --- |
| Querydsl | `QuerydslPredicateExecutor<T>` | `QuerydslDataFetcher.builder(repository)` |
| Query by Example | `QueryByExampleExecutor<T>` | `QueryByExampleDataFetcher.builder(repository)` |

Querydsl phù hợp khi cần predicate linh hoạt và type-safe. Query by Example phù hợp với các tiêu chí tìm kiếm đơn giản dựa trên example object. Cả hai có thể tạo DataFetcher và đăng ký qua `RuntimeWiringConfigurer`.

Ví dụ tạo DataFetcher nhiều kết quả bằng Querydsl:

```java
DataFetcher<Iterable<Book>> booksFetcher =
        QuerydslDataFetcher.builder(bookRepository).many();
```

Với paginated query, Spring for GraphQL cung cấp builder method `scrollable()`. API này làm việc với Spring Data scrolling và `Window`; nếu cấu hình cursor strategy, nó có thể biểu diễn pagination theo cursor. Không nhầm scrolling/cursor connection này với GraphQL field tự định nghĩa `offset` và `limit` ở các phần trước.

Tài liệu Data Integration mô tả rõ auto-registration offset-based 20 item mặc định. Hãy xác minh schema connection và hành vi argument thực tế theo phiên bản Spring for GraphQL/Spring Data mà ứng dụng đang dùng trước khi dùng auto-registration làm hợp đồng public.

## 8. Vì sao offset lớn chậm?

Offset pagination đơn giản ở phía client nhưng có thể tốn kém ở database. Khi request:

```sql
SELECT id, title
FROM books
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 500000;
```

Database thường vẫn phải đi qua hoặc materialize nhiều kết quả trước vị trí 500.000 rồi mới trả 20 hàng tiếp theo. Cách thực thi chính xác phụ thuộc database, query plan và index, nhưng chi phí thường tăng khi offset tăng.

Ví dụ minh họa:

| Offset | Limit | Công việc database có thể phải làm |
| ---: | ---: | --- |
| 0 | 20 | Đọc phần đầu của thứ tự kết quả |
| 1.000 | 20 | Bỏ qua khoảng 1.000 hàng trước khi trả 20 hàng |
| 100.000 | 20 | Có thể phải duyệt/bỏ qua lượng lớn hàng |
| 1.000.000 | 20 | Có thể rất tốn I/O và CPU tùy query plan |

Đây là lý do offset pagination thường phù hợp với tập dữ liệu có quy mô vừa, giao diện cần nhảy đến trang bất kỳ hoặc dữ liệu được lọc mạnh. Với feed lớn và truy cập sâu, keyset/cursor pagination thường hiệu quả hơn.

### Tạo index khớp với filter và sort

Nếu query thường dùng:

```sql
WHERE status = 'PUBLISHED'
ORDER BY created_at DESC, id DESC
```

cân nhắc index phù hợp với filter và thứ tự sắp xếp, ví dụ:

```sql
CREATE INDEX idx_books_status_created_id
ON books (status, created_at DESC, id DESC);
```

Index cụ thể phụ thuộc database, selectivity của filter, chiều sort và các query khác. Dùng execution plan để xác nhận database có sử dụng index; không tạo index chỉ dựa vào tên cột trong ví dụ.

### Chỉ chọn các cột cần thiết

GraphQL selection set có thể chỉ yêu cầu `id` và `title`. Nếu entity có nhiều cột lớn hoặc quan hệ eager, tải toàn entity có thể làm tăng I/O và memory. Dùng projection hoặc DTO phù hợp nếu query chỉ cần một phần dữ liệu.

## 9. Thứ tự sắp xếp phải ổn định

Offset pagination dựa vào vị trí của bản ghi trong danh sách đã sắp xếp. Nếu thứ tự không ổn định, cùng một offset có thể trỏ tới những bản ghi khác nhau giữa các request.

Ví dụ không đủ ổn định:

```sql
ORDER BY created_at DESC
```

Nhiều bản ghi có thể có cùng `created_at`. Hãy thêm một khóa duy nhất làm tie-breaker:

```sql
ORDER BY created_at DESC, id DESC
```

Thứ tự này tạo ra một chuỗi kết quả xác định hơn. Nếu client được phép chọn sort, server vẫn nên bổ sung khóa duy nhất ở cuối để phá hòa.

### Sort input có whitelist

Không ghép trực tiếp chuỗi sort do client gửi vào JPQL hoặc SQL. Hãy dùng enum:

```graphql
enum BookSort {
  NEWEST
  TITLE_ASC
}

type Query {
  books(offset: Int = 0, limit: Int = 20, sort: BookSort = NEWEST): BookPage!
}
```

Trong service, map enum sang biểu thức sort cố định:

```java
Sort sort = switch (requestedSort) {
    case NEWEST -> Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id"));
    case TITLE_ASC -> Sort.by(
            Sort.Order.asc("title"),
            Sort.Order.asc("id"));
};
```

Không cho client truyền tên cột tùy ý nếu chưa kiểm tra whitelist. Tên cột động có thể tạo lỗi query, lộ thuộc tính nội bộ hoặc mở rộng bề mặt tấn công.

## 10. Dữ liệu thay đổi giữa các trang

Ngay cả khi có thứ tự ổn định, offset pagination vẫn có thể lặp hoặc bỏ sót bản ghi khi dữ liệu thay đổi giữa hai request.

Giả sử client đã lấy trang đầu gồm các bản ghi ở vị trí 0–19. Trước khi client gọi offset 20, một bản ghi mới được chèn vào đầu danh sách:

```text
Trước khi insert:
0  1  2  ...  19 | 20  21  22 ...
<--- trang 1 ---> | <--- trang 2 --->

Sau khi insert ở đầu:
NEW 0  1 ... 17 18 | 19 20 21 ...
<----- trang 1 ----> | <--- trang 2 --->
```

Khi client tiếp tục gọi offset 20, một số bản ghi có thể xuất hiện lại so với trang trước. Nếu có bản ghi bị xóa trước vị trí offset, client có thể bỏ qua một bản ghi mà chưa từng nhìn thấy.

Đây là đặc điểm của offset pagination trên tập dữ liệu thay đổi liên tục, không nhất thiết là lỗi của GraphQL hoặc repository.

Các lựa chọn giảm rủi ro:

- Dùng thứ tự sắp xếp ổn định với khóa duy nhất.
- Dùng filter hoặc mốc thời gian cố định cho toàn bộ lượt duyệt nếu nghiệp vụ cho phép.
- Dùng transaction snapshot khi toàn bộ việc đọc nằm trong cùng một transaction; không thể giả định transaction được giữ xuyên qua nhiều HTTP request độc lập.
- Dùng cursor/keyset pagination nếu cần duyệt tập dữ liệu lớn thường xuyên thay đổi.
- Làm cho client có khả năng loại trùng theo ID nếu trải nghiệm cho phép.

Không hứa hẹn tính nhất quán snapshot qua nhiều page request nếu server không thực sự giữ snapshot hoặc token truy vấn tương ứng.

## 11. Offset pagination và Spring Data Pageable

Spring Data dùng `Pageable` để biểu diễn page number, page size và sort. Đây là mô hình page-based:

```java
Page<Book> findAll(Pageable pageable);
```

Client thường truyền `page` và `size`, sau đó server tạo:

```java
PageRequest.of(page, size, sort);
```

Offset được tính bằng:

```text
offset = page * size
```

Vì vậy, `Pageable` phù hợp khi API muốn phân trang theo số trang và mọi offset là bội số của page size. Nếu GraphQL contract cho phép offset tùy ý, ví dụ `offset = 15` và `limit = 20`, chuyển trực tiếp sang `PageRequest.of(offset / limit, limit)` sẽ làm mất ý nghĩa của offset vì phép chia lấy phần nguyên.

Với offset tùy ý:

- Dùng JPA `setFirstResult(offset)` và `setMaxResults(limit)`.
- Dùng query API của persistence provider hỗ trợ offset/limit trực tiếp.
- Hoặc xây dựng abstraction riêng để repository nhận offset và limit.

Không biến một offset tùy ý thành page number bằng cách chia cho limit nếu API không đảm bảo offset chia hết cho limit.

## 12. Filter và authorization phải được áp dụng trước khi phân trang

Nếu query hỗ trợ filter, server phải áp dụng filter trước khi tính offset và limit:

```graphql
input BookFilterInput {
  status: String
  authorId: ID
}

type Query {
  books(
    offset: Int = 0
    limit: Int = 20
    filter: BookFilterInput
  ): BookPage!
}
```

Thứ tự xử lý logic:

1. Xác định người dùng và tenant từ security context.
2. Áp dụng điều kiện authorization/tenant.
3. Áp dụng filter do client yêu cầu.
4. Sắp xếp theo thứ tự ổn định.
5. Áp dụng offset và limit.
6. Tính metadata như hasNextPage hoặc totalCount.

Không lấy một trang toàn cục rồi lọc quyền truy cập trong Java sau khi database đã áp dụng offset. Cách đó có thể trả về trang thiếu item, sai hasNextPage và vô tình làm lộ thông tin qua totalCount.

Ví dụ nếu user chỉ được xem sách thuộc tenant của họ, cả truy vấn lấy item và count query đều phải có điều kiện tenant:

```sql
SELECT id, title
FROM books
WHERE tenant_id = :tenantId
ORDER BY created_at DESC, id DESC
LIMIT :limit OFFSET :offset;
```

```sql
SELECT COUNT(*)
FROM books
WHERE tenant_id = :tenantId;
```

Nếu có filter status, cả hai truy vấn đều phải áp dụng status đó. Authorization là điều kiện của tập kết quả, không phải bước làm sạch response sau truy vấn.

## 13. Tránh N+1 trong các field lồng nhau của trang

Offset pagination chỉ giới hạn số parent object được trả về. Nếu mỗi Book có field Author và resolver gọi repository một lần cho mỗi sách, một trang 20 sách vẫn có thể tạo 21 truy vấn.

Ví dụ query:

```graphql
query {
  books(offset: 0, limit: 20) {
    items {
      id
      title
      author {
        id
        name
      }
    }
  }
}
```

Kết hợp `@BatchMapping` hoặc `DataLoader` để gom việc tải author:

```java
@BatchMapping(typeName = "Book", field = "author")
public Mono<Map<Book, Author>> author(List<Book> books) {
    return authorService.findByBooks(books)
            .collectMap(AuthorEntry::book, AuthorEntry::author);
}
```

Như vậy, phân trang giới hạn số Book ở root query, còn DataLoader/BatchMapping giảm số lần tải dữ liệu liên quan. Hai kỹ thuật giải quyết hai vấn đề hiệu năng khác nhau và thường cần dùng cùng nhau.

## 14. Kiểm thử offset pagination

Nên kiểm thử cả hợp đồng GraphQL và quy tắc repository:

- Offset mặc định bằng 0 và limit mặc định bằng 20 khi client bỏ qua arguments.
- Trang đầu và trang tiếp theo không bị trùng khi dữ liệu không thay đổi.
- Trang cuối có ít item hơn limit và `hasNextPage = false`.
- Offset vượt cuối tập kết quả trả list rỗng, metadata vẫn nhất quán.
- Limit bằng 0, âm hoặc vượt max bị từ chối.
- Các bản ghi có cùng sort key vẫn có thứ tự ổn định nhờ tie-breaker.
- Filter và tenant authorization áp dụng giống nhau cho item query và count query.
- GraphQL response không trả tổng số bản ghi ngoài phạm vi người dùng được phép xem.

Ví dụ dùng `GraphQlTester` trong test slice:

```java
import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;

@GraphQlTest(BookController.class)
class BookPaginationTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @Test
    void returnsRequestedOffsetAndLimit() {
        given(bookService.findBooks(20, 10))
                .willReturn(new BookPage(
                        List.of(new Book("book-21", "Spring GraphQL")),
                        20,
                        10,
                        true));

        GraphQlTester.Response response = graphQlTester.document("""
                query {
                    books(offset: 20, limit: 10) {
                        offset
                        limit
                        hasNextPage
                        items {
                            id
                        }
                    }
                }
                """)
                .execute();

        response.path("books.offset").entity(Integer.class).isEqualTo(20);
        response.path("books.limit").entity(Integer.class).isEqualTo(10);
        response.path("books.hasNextPage").entity(Boolean.class).isEqualTo(true);
        response.path("books.items[0].id").entity(String.class).isEqualTo("book-21");

        then(bookService).should().findBooks(20, 10);
    }
}
```

Ví dụ dùng `@MockitoBean` theo Spring Boot hiện hành. Với phiên bản Boot cũ, annotation mock bean có thể là `@MockBean`. Test giả định schema và controller có field `books` như các phần trước.

### Kiểm thử repository

GraphQL slice test thường mock service, vì vậy nó không chứng minh SQL/JPA thực thi offset đúng. Bổ sung repository integration test với database phù hợp để xác nhận:

- Query trả đúng bản ghi ở offset đã chọn.
- Thứ tự không đổi khi nhiều bản ghi có cùng createdAt.
- Count query và data query dùng cùng filter.
- Index được sử dụng theo execution plan ở môi trường gần production.

Không cần dùng live HTTP server để kiểm tra logic offset của repository; test persistence có thể chạy trực tiếp qua Spring Data/JPA.

## 15. Lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Trang đầu và trang sau bị trùng item | Sort không có tie-breaker duy nhất hoặc dữ liệu thay đổi | Thêm khóa duy nhất vào ORDER BY; cân nhắc cursor |
| Bỏ sót item giữa các trang | Bản ghi bị chèn/xóa trước vị trí offset | Chấp nhận đặc tính offset hoặc dùng cursor/keyset |
| Request offset lớn rất chậm | Database phải bỏ qua nhiều hàng | Giới hạn offset, thêm index hoặc chuyển sang keyset |
| Page có ít item dù vẫn còn dữ liệu | Filter/authorization được áp dụng sau khi phân trang | Áp dụng mọi điều kiện trong query trước limit/offset |
| totalCount không khớp items | Count query và data query khác filter hoặc khác phạm vi quyền | Dùng cùng predicate và tenant condition |
| Không lấy đúng offset khi dùng PageRequest | Chuyển offset tùy ý thành page number bằng phép chia | Dùng API offset trực tiếp |
| Limit quá lớn làm response nặng | Không có maximum page size | Validate và giới hạn limit |
| totalCount bị lỗi GraphQL Int | Giá trị long vượt phạm vi 32-bit | Dùng custom scalar/chuỗi hoặc giới hạn hợp đồng |
| Trang có thứ tự thay đổi ngẫu nhiên | Sort theo cột không duy nhất | Thêm ID làm tie-breaker |
| Một trang nhỏ vẫn phát sinh nhiều query | Nested field resolver gặp N+1 | Dùng DataLoader hoặc @BatchMapping |
| Query sort có thể bị thao túng | Ghép raw sort string vào SQL/JPQL | Dùng enum và whitelist sort field |

## 16. Khi nào nên chuyển sang cursor/keyset pagination?

Offset pagination có lợi thế dễ hiểu, dễ triển khai và hỗ trợ nhảy đến trang bất kỳ. Nhưng nếu client thường xuyên đi sâu vào hàng trăm nghìn hoặc hàng triệu bản ghi, offset có thể gây chi phí cao.

Keyset pagination dùng giá trị của bản ghi cuối trang hiện tại làm vị trí tiếp tục. Ví dụ sort theo `createdAt DESC, id DESC`, trang sau có điều kiện:

```sql
WHERE created_at < :lastCreatedAt
   OR (created_at = :lastCreatedAt AND id < :lastId)
ORDER BY created_at DESC, id DESC
LIMIT :limit;
```

Database có thể tận dụng index trên sort keys để tìm phần tiếp theo mà không cần bỏ qua tất cả hàng trước đó. Cursor thường mã hóa các sort keys này và được gửi lại ở request kế tiếp.

Chọn cách phân trang theo nhu cầu:

| Nhu cầu | Lựa chọn phù hợp |
| --- | --- |
| Trang nhỏ, số lượng dữ liệu vừa | Offset/limit |
| UI cần nhảy đến số trang bất kỳ | Offset/limit |
| Duyệt feed lớn, liên tục có bản ghi mới | Cursor/keyset |
| Muốn dùng Spring Data Window/ScrollPosition | Scroll API và ConnectionAdapter |
| Cần tổng số bản ghi chính xác | Offset + count query, nếu chi phí chấp nhận được |

Spring for GraphQL hỗ trợ GraphQL Connection types và Spring Data Window/Slice adapters cho cursor-based pagination. Đây là một hướng nâng cấp khi offset pagination không còn phù hợp; không cần ép mọi API phải dùng cursor ngay từ đầu.

## 17. Nguyên tắc triển khai offset pagination

- Định nghĩa rõ offset là số hàng bỏ qua, limit là số hàng tối đa trả về.
- Đặt default và maximum limit trong schema/service.
- Validate offset không âm, limit dương và giới hạn hợp lý.
- Dùng ORDER BY ổn định với khóa duy nhất làm tie-breaker.
- Dùng `limit + 1` để tính hasNextPage nếu không cần totalCount.
- Chỉ chạy count query khi client thực sự cần tổng số bản ghi.
- Áp dụng filter, tenant và authorization trước offset/limit.
- Dùng index khớp với filter và sort; kiểm tra execution plan.
- Tránh offset quá lớn; cân nhắc cursor/keyset khi dữ liệu tăng.
- Dùng DataLoader hoặc @BatchMapping cho field lồng nhau của từng item.
- Không ghép raw sort string từ client vào SQL/JPQL.
- Kiểm thử cả GraphQL resolver và repository query.
- Không hứa hẹn snapshot consistency qua nhiều request nếu không có cơ chế đảm bảo.

## 18. Bài tập thực hành

Xây dựng API tìm sách có offset pagination:

1. Khai báo GraphQL field `books(offset, limit)` và type `BookPage`.
2. Viết `@QueryMapping` nhận hai argument bằng `@Argument`.
3. Validate offset và limit, giới hạn limit tối đa 100.
4. Viết repository JPA dùng `setFirstResult` và `setMaxResults`.
5. Sắp xếp theo createdAt và ID để tạo thứ tự ổn định.
6. Lấy `limit + 1` item để xác định `hasNextPage`.
7. Bổ sung filter status và áp dụng cùng filter cho item query/count query.
8. Thêm tenant condition trước khi phân trang.
9. Viết query lấy danh sách sách và author; dùng `@BatchMapping` để tránh N+1.
10. Viết GraphQlTester test cho trang đầu, trang tiếp theo, trang cuối và input không hợp lệ.
11. Viết repository integration test xác minh offset và sort.
12. Đo thời gian query ở offset nhỏ và offset lớn; xem execution plan.
13. Đề xuất tiêu chí chuyển sang cursor/keyset pagination.

Sau bài tập, bạn cần giải thích được cách offset/limit được truyền từ GraphQL xuống database, vì sao sort phải ổn định, khi nào cần count query và tại sao offset sâu có thể làm truy vấn chậm.

## 19. Tài liệu tham khảo

- [Spring for GraphQL — Data Integration and @GraphQlRepository](https://docs.spring.io/spring-graphql/reference/data.html)
- [Spring for GraphQL — Annotated Controllers and @Argument](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Request Execution and Pagination](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Data JPA — Paging and Sorting](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html)
- [Spring Data JPA — Scrolling and Offset](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [GraphQL Specification — Int Scalar](https://spec.graphql.org/September2026/#sec-Int)

Offset pagination là một lựa chọn đơn giản cho tập dữ liệu vừa và UI cần điều hướng theo vị trí. Khi dữ liệu lớn hoặc thay đổi liên tục, hãy đánh giá cursor/keyset pagination cùng các cơ chế scrolling mà Spring for GraphQL và Spring Data cung cấp.
