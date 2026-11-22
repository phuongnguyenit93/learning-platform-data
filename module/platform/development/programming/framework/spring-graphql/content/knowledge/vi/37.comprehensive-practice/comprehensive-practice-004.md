# Sửa N+1 bằng @BatchMapping

Trong bài thực hành này, ta xây dựng một GraphQL query trả về danh sách sách cùng tác giả. Phiên bản đầu dùng `@SchemaMapping` để tải tác giả riêng cho từng sách, tạo ra lỗi N+1. Sau đó ta thay resolver bằng `@BatchMapping`, gom các sách trong cùng lần thực thi, lấy tác giả theo tập ID và ánh xạ kết quả trở lại đúng sách.

Mục tiêu không chỉ là làm số câu SQL giảm xuống. Ta còn phải bảo đảm kết quả vẫn đúng khi nhiều sách dùng chung tác giả, một sách không có tác giả, dữ liệu bị thiếu hoặc người dùng chỉ được phép xem một phần dữ liệu. Cuối bài, ta sẽ đo và kiểm thử để xác nhận batch hoạt động thật sự.

## 1. Kết quả cần đạt

Sau bài thực hành, bạn có thể:

- Nhận diện N+1 từ hình dạng GraphQL query và số lần truy cập database.
- Viết resolver field bằng `@SchemaMapping` và giải thích vì sao nó tạo N+1.
- Dùng `@BatchMapping` để gom nhiều source object trong một batch.
- Truy vấn các khóa duy nhất, lập map kết quả và gắn đúng giá trị cho từng source object.
- Xử lý ID null, bản ghi không tồn tại, phân trang, tenant và quyền truy cập.
- Kiểm tra số lần gọi repository/service và so sánh trước/sau khi tối ưu.

## 2. Bối cảnh và cấu trúc dữ liệu

Giả sử API quản lý sách. Mỗi sách có một tác giả; nhiều sách có thể cùng tác giả. Client muốn lấy danh sách sách và thông tin tác giả trong một operation.

Schema SDL:

```graphql
type Query {
    books: [Book!]!
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
```

`Book.author` được để nullable vì dữ liệu có thể chưa gán tác giả hoặc tác giả đã bị xóa theo chính sách dữ liệu. Nếu nghiệp vụ bắt buộc mọi sách đều có tác giả, hãy đổi thành `Author!` và xác định rõ cách xử lý dữ liệu vi phạm ràng buộc.

Mô hình Java dùng trong ví dụ:

```java
public record Book(UUID id, String title, UUID authorId) {}

public record Author(UUID id, String name) {}
```

`Book` chỉ giữ `authorId`; nó không có thuộc tính `author` để Spring tự đọc. Field `Book.author` trong GraphQL sẽ do resolver của chúng ta cung cấp.

Giả sử `BookService.findAll()` trả về ba sách sau:

| Sách | Tác giả |
|---|---|
| B-101 | A-01 |
| B-102 | A-02 |
| B-103 | A-01 |

Hai sách dùng chung tác giả A-01. Đây là trường hợp quan trọng để kiểm tra việc loại ID trùng trước khi truy vấn.

## 3. Query GraphQL dùng để tái hiện

Client gửi operation:

```graphql
query BooksWithAuthors {
    books {
        id
        title
        author {
            id
            name
        }
    }
}
```

Query yêu cầu ba sách và field `author` của từng sách. Nếu chỉ yêu cầu `id` và `title`, resolver `author` không cần chạy. Vì vậy khi điều tra N+1, hãy dùng đúng query shape đang gây chậm; chỉ gọi endpoint mà không yêu cầu field quan hệ sẽ không tái hiện được vấn đề.

## 4. Bước 1 — Viết resolver đơn lẻ và quan sát N+1

Resolver gốc của query:

```java
@Controller
class BookController {

    private final BookService bookService;
    private final AuthorService authorService;

    BookController(BookService bookService, AuthorService authorService) {
        this.bookService = bookService;
        this.authorService = authorService;
    }

    @QueryMapping
    List<Book> books() {
        return bookService.findAll();
    }

    @SchemaMapping(typeName = "Book", field = "author")
    Author author(Book book) {
        if (book.authorId() == null) {
            return null;
        }
        return authorService.findById(book.authorId()).orElse(null);
    }
}
```

`@SchemaMapping` được gọi cho field `Book.author` trên từng object `Book`. Với ba sách, quá trình thực thi có thể tương đương:

```sql
SELECT id, title, author_id FROM book;
SELECT id, name FROM author WHERE id = 'A-01';
SELECT id, name FROM author WHERE id = 'A-02';
SELECT id, name FROM author WHERE id = 'A-01';
```

Ta có một truy vấn lấy danh sách sách và ba truy vấn lấy tác giả: tổng cộng bốn truy vấn. Khi danh sách tăng lên 100 sách, phần tải tác giả có thể phát sinh 100 truy vấn. Đó là mẫu N+1.

Trong thực tế, số truy vấn có thể khác do ORM, cache cấp một, cache ứng dụng hoặc cách repository triển khai. Không kết luận chỉ từ code. Hãy bật SQL logging ở môi trường phát triển hoặc dùng tracing/query metrics để đếm truy vấn trên một GraphQL request. Cache có thể che bớt truy vấn lặp trong ví dụ nhưng không giải quyết được chi phí tải từng tác giả khác nhau.

## 5. Bước 2 — Chuẩn bị hàm truy vấn theo tập ID

Batch chỉ hiệu quả nếu tầng dữ liệu có thể tải nhiều tác giả trong một thao tác. Ta định nghĩa service trả về map theo ID:

```java
@Service
class AuthorService {

    private final AuthorRepository authorRepository;

    AuthorService(AuthorRepository authorRepository) {
        this.authorRepository = authorRepository;
    }

    Optional<Author> findById(UUID id) {
        return authorRepository.findById(id);
    }

    Map<UUID, Author> findByIds(Collection<UUID> ids) {
        if (ids.isEmpty()) {
            return Map.of();
        }

        return authorRepository.findByIdIn(ids).stream()
                .collect(Collectors.toMap(Author::id, Function.identity()));
    }
}
```

Repository trong ví dụ có phương thức truy vấn theo tập ID:

```java
interface AuthorRepository {
    Optional<Author> findById(UUID id);

    List<Author> findByIdIn(Collection<UUID> ids);
}
```

Nếu dùng Spring Data JPA, có thể khai báo phương thức truy vấn dẫn xuất tương ứng trên repository của entity. Nếu dùng JDBC hoặc một data access layer khác, triển khai bằng một câu truy vấn có điều kiện `WHERE id IN (...)` hoặc cơ chế bulk query tương đương. Điều cần xác nhận là phương thức này thực sự thực hiện truy vấn theo tập ID, không lặp lại một truy vấn đơn bên trong vòng lặp.

Khi tập ID rỗng, trả về map rỗng và không gửi câu `IN ()` xuống database. Khi chuyển kết quả sang map, ID của từng tác giả phải duy nhất; nếu dữ liệu có thể chứa trùng, cần xử lý rõ thay vì âm thầm ghi đè.

## 6. Bước 3 — Thay `@SchemaMapping` bằng `@BatchMapping`

Sau khi đã có API truy vấn theo tập ID, thay resolver đơn lẻ bằng resolver theo batch:

```java
@Controller
class BookController {

    private final BookService bookService;
    private final AuthorService authorService;

    BookController(BookService bookService, AuthorService authorService) {
        this.bookService = bookService;
        this.authorService = authorService;
    }

    @QueryMapping
    List<Book> books() {
        return bookService.findAll();
    }

    @BatchMapping(typeName = "Book", field = "author")
    Map<Book, Author> author(List<Book> books) {
        Set<UUID> authorIds = books.stream()
                .map(Book::authorId)
                .filter(Objects::nonNull)
                .collect(Collectors.toSet());

        Map<UUID, Author> authors = authorService.findByIds(authorIds);
        Map<Book, Author> result = new HashMap<>();

        for (Book book : books) {
            Author author = book.authorId() == null
                    ? null
                    : authors.get(book.authorId());
            result.put(book, author);
        }

        return result;
    }
}
```

Các import Java cần có cho phần ví dụ:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;
```

`@BatchMapping(typeName = "Book", field = "author")` liên kết phương thức với field `Book.author` trong schema. Spring for GraphQL đăng ký batch loader và DataLoader tương ứng. Khi quá trình thực thi cần resolve field này cho nhiều sách, các source object được gom lại và truyền vào tham số `List<Book>`.

Phương thức trả về `Map<Book, Author>`. Mỗi key là source object `Book`, mỗi value là kết quả cho field `author` của source đó. Map giúp ánh xạ rõ ràng, không phụ thuộc thứ tự mà repository trả về các tác giả. Điều này quan trọng vì truy vấn `WHERE id IN (...)` không bảo đảm thứ tự bản ghi giống thứ tự ID đầu vào.

Với dữ liệu mẫu, tập ID sau khi loại trùng là `{A-01, A-02}`. Database chỉ cần một truy vấn lấy hai tác giả. Resolver lập map kết quả cho cả ba sách, trong đó B-101 và B-103 cùng nhận tác giả A-01.

## 7. Hiểu luồng batch và DataLoader

Luồng xử lý có thể hình dung như sau:

```mermaid
flowchart TD
    A[Query books] --> B[BookService trả về nhiều Book]
    B --> C[GraphQL yêu cầu field Book.author]
    C --> D[DataLoader gom các Book cần resolve]
    D --> E[@BatchMapping nhận List<Book>]
    E --> F[Thu thập authorId và loại trùng]
    F --> G[AuthorService truy vấn theo tập ID]
    G --> H[Lập Map<Book, Author>]
    H --> I[GraphQL hoàn thiện response]
```

DataLoader giúp trì hoãn và gom các lần nạp dữ liệu trong quá trình thực thi GraphQL. `@BatchMapping` là cách khai báo batch resolver tiện lợi, Spring đăng ký loader dựa trên phương thức này. Batch hoạt động trong phạm vi lần thực thi request; không phải cache phân tán và không tự động làm mới dữ liệu giữa các request.

Kích thước batch thực tế phụ thuộc số source object cần resolve, cách thực thi và giới hạn batch được cấu hình. Với danh sách lớn, một lần thực thi có thể được chia thành nhiều batch. Do đó, mục tiêu là giảm số lần truy cập backend theo nhóm hợp lý, không giả định mọi kích thước đầu vào luôn tạo đúng một câu SQL.

## 8. Bước 4 — So sánh số truy vấn trước và sau

Với ba sách ở dữ liệu mẫu:

| Cách triển khai | Truy vấn lấy sách | Truy vấn lấy tác giả | Tổng |
|---|---:|---:|---:|
| `@SchemaMapping` gọi `findById` từng sách | 1 | 3 | 4 |
| `@BatchMapping` gọi `findByIds` một lần | 1 | 1 | 2 |

Đây là số truy vấn kỳ vọng khi batch chứa cả ba sách và database adapter thực hiện đúng một bulk query. Khi đo thực tế, hãy đếm câu SQL và số lần gọi service, không chỉ đếm số lần phương thức `@BatchMapping` chạy.

Với 100 sách và 100 tác giả khác nhau, cách đơn lẻ có thể tạo 101 truy vấn; batch có thể tạo 2 truy vấn nếu toàn bộ sách nằm trong một batch và không có giới hạn chia lô. Nếu 100 sách chỉ tham chiếu 5 tác giả, việc dùng `Set<UUID>` còn giảm tập khóa truyền xuống database còn 5 ID.

## 9. Bước 5 — Kiểm thử kết quả GraphQL

Kiểm thử phải xác nhận đồng thời hai điều: dữ liệu trả về đúng và số lần truy cập backend giảm. Chỉ kiểm tra response là chưa đủ vì resolver N+1 vẫn có thể trả về dữ liệu hoàn toàn chính xác.

Với `GraphQlTester`, hãy cấu hình test slice cho controller, cung cấp mock cho `BookService` và `AuthorService`, rồi gửi query `BooksWithAuthors`. Tên annotation khai báo mock phụ thuộc phiên bản Spring Boot/Spring Framework đang dùng (`@MockitoBean` ở các phiên bản mới hoặc `@MockBean` ở các phiên bản trước).

Ví dụ phần kiểm tra chính:

```java
@Test
void resolvesAuthorsInBatch() {
    // bookService trả về B-101 -> A-01, B-102 -> A-02, B-103 -> A-01.
    // authorService.findByIds(Set.of(A01, A02)) trả về hai tác giả.

    graphQlTester.document("""
            query {
                books {
                    id
                    title
                    author { id name }
                }
            }
            """)
            .execute()
            .path("books")
            .entityList(BookGraphQlView.class);

    then(authorService).should(times(1))
            .findByIds(Set.of(A01, A02));
}
```

`BookGraphQlView` là DTO test có các trường `id`, `title` và `author`; `A01`, `A02` là UUID fixture của test. Hoàn thiện assertion trên DTO để xác nhận B-101 và B-103 nhận cùng tác giả A-01, B-102 nhận A-02. Nếu test dùng Mockito, có thể dùng `ArgumentCaptor` để kiểm tra chính xác tập ID truyền vào service.

Với phiên bản resolver cũ, kiểm tra `findById` được gọi theo số sách có `authorId` hợp lệ. Sau khi chuyển sang batch, kiểm tra `findByIds` được gọi theo số batch thực tế và không có lời gọi `findById` lặp cho từng sách. Không nên hardcode kỳ vọng một batch cho test có kích thước vượt giới hạn batch đã cấu hình.

## 10. Bước 6 — Xử lý trường hợp biên

### Sách không có authorId

Ví dụ B-104 có `authorId = null`. Không đưa null vào tập ID truy vấn. Khi lập kết quả, vẫn thêm key B-104 với value null. Điều này bảo đảm field `author` trả về null theo schema đã khai báo.

### Không tìm thấy tác giả

Nếu sách tham chiếu ID không tồn tại, `authors.get(id)` trả về null. Cần quyết định đây là dữ liệu thiếu có thể chấp nhận, lỗi toàn vẹn dữ liệu hay tình huống cần trả GraphQL error. Quyết định phải phù hợp nullability của SDL và quy tắc nghiệp vụ.

### Danh sách sách rỗng

Nếu `books` rỗng, tập ID cũng rỗng. `findByIds` trả `Map.of()` mà không truy vấn database. Batch resolver trả map rỗng.

### Nhiều sách cùng tác giả

`Set<UUID>` loại ID trùng để truy vấn tác giả một lần. Khi lập kết quả, mỗi sách vẫn có một entry riêng trỏ đến cùng đối tượng tác giả. Không tạo kết quả theo vị trí của danh sách ID vì thứ tự truy vấn database không được bảo đảm.

### Một phần dữ liệu không được phép xem

Nếu quyền xem tác giả phụ thuộc tenant hoặc người dùng, áp dụng điều kiện đó trong `findByIds` hoặc service được gọi. Không tải tất cả tác giả theo ID rồi trả dữ liệu mà không kiểm tra phạm vi truy cập. Nếu một tác giả không được phép xem, quyết định trả null hay phát sinh lỗi field theo chính sách authorization và schema.

## 11. Bước 7 — Giữ đúng ranh giới tenant và bảo mật

Batch gom nhiều source object trong cùng lần thực thi, vì vậy service phải xử lý tập khóa như một đơn vị nhưng vẫn giữ đầy đủ điều kiện truy cập. Ví dụ, thay vì chỉ truy vấn:

```sql
SELECT id, name
FROM author
WHERE id IN (:ids);
```

ứng dụng đa tenant cần giới hạn tenant:

```sql
SELECT id, name
FROM author
WHERE tenant_id = :tenantId
  AND id IN (:ids);
```

`tenantId` phải lấy từ ngữ cảnh bảo mật đã được xác thực ở server, không tin giá trị do client tự gửi trong query. Nếu quyền truy cập phụ thuộc từng tác giả, service cần áp dụng quy tắc đó cho mọi ID trong batch.

Không dùng một map cache tĩnh hoặc cache dùng chung giữa người dùng cho kết quả phụ thuộc tenant/authorization. DataLoader của GraphQL được dùng trong phạm vi thực thi request; vẫn cần cẩn thận nếu tự cấu hình loader, cache hoặc service singleton. Không đưa dữ liệu nhạy cảm vào metric label hay log khóa truy vấn.

## 12. Bước 8 — Xử lý batch lớn và phân trang

Batch giúp giảm số lần gọi nhưng không loại bỏ giới hạn của database. Một câu `IN` có quá nhiều tham số có thể vượt giới hạn driver/database hoặc tạo query plan kém. Hãy:

- Giới hạn page size ở resolver query gốc.
- Cấu hình giới hạn batch phù hợp với database và dịch vụ phụ thuộc nếu phiên bản/cấu hình Spring for GraphQL hỗ trợ.
- Chia tập ID thành các nhóm khi service cần kiểm soát số bind parameter.
- Theo dõi số khóa mỗi batch, thời gian truy vấn và số batch trên một operation.
- Tránh trả về danh sách không giới hạn rồi trông chờ DataLoader giải quyết toàn bộ chi phí.

Ví dụ chia tập ID thành từng nhóm trong service (chỉ dùng khi cần thiết):

```java
Map<UUID, Author> findByIdsInChunks(Collection<UUID> ids, int chunkSize) {
    if (chunkSize <= 0) {
        throw new IllegalArgumentException("chunkSize must be greater than zero");
    }
    if (ids.isEmpty()) {
        return Map.of();
    }

    Map<UUID, Author> result = new HashMap<>();
    List<UUID> allIds = new ArrayList<>(ids);

    for (int start = 0; start < allIds.size(); start += chunkSize) {
        int end = Math.min(start + chunkSize, allIds.size());
        List<UUID> chunk = allIds.subList(start, end);
        for (Author author : authorRepository.findByIdIn(chunk)) {
            result.put(author.id(), author);
        }
    }

    return result;
}
```

`chunkSize` phải là cấu hình có căn cứ từ giới hạn hệ thống và số tham số truy vấn, đồng thời cần xác thực lớn hơn 0. Đo số truy vấn phát sinh sau khi chia lô để bảo đảm giới hạn được xử lý có kiểm soát.

## 13. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Giữ cả `@SchemaMapping` và `@BatchMapping` cho cùng `Book.author` | Hai data fetcher cạnh tranh cho một field hoặc cấu hình không rõ ràng | Thay resolver cũ bằng batch resolver |
| Dùng `findById` bên trong vòng lặp batch | N+1 vẫn tồn tại ở tầng service | Dùng một API truy vấn theo tập ID |
| Trả `List<Author>` theo thứ tự repository | Tác giả có thể gắn nhầm sách nếu thứ tự khác nhau | Trả `Map<Book, Author>` hoặc tự bảo đảm thứ tự theo hợp đồng loader |
| Không loại ID trùng | Truy vấn lặp khóa không cần thiết | Thu thập ID bằng `Set` |
| Dùng `Map.of(book, null)` | Java ném `NullPointerException` | Dùng `HashMap` nếu cần giá trị null hoặc xử lý null theo chính sách khác |
| Bỏ qua tenant filter | Có nguy cơ lộ dữ liệu chéo tenant | Áp dụng tenant và authorization trong service batch |
| Không giới hạn danh sách | Batch quá lớn, response và truy vấn tốn tài nguyên | Pagination và giới hạn batch |
| Chỉ đo latency tổng | Không biết số truy vấn có giảm hay không | Đo SQL count, batch size, service call count và trace |

## 14. Thực hành mở rộng

Sau khi hoàn thành ví dụ sách và tác giả, tự triển khai thêm các tình huống:

1. Một sách có nhiều thể loại. Viết `@BatchMapping` cho `Book.categories` và trả `Map<Book, List<Category>>`.
2. Một tác giả có thể bị ẩn theo tenant. Đảm bảo batch không trả thông tin tác giả ngoài tenant hiện tại.
3. Một trang có 500 sách. Đặt page size và giới hạn batch; đo số truy vấn khi batch bị chia nhỏ.
4. Một số sách có `authorId` không tồn tại. Xác định response và GraphQL error theo nullability của schema.
5. So sánh `@BatchMapping` với việc đăng ký DataLoader tường minh qua `BatchLoaderRegistry`. Chọn cách phù hợp khi logic batch phức tạp hoặc cần tái sử dụng loader.

## 15. Tiêu chí hoàn thành bài thực hành

- [ ] Query GraphQL trả danh sách sách cùng thông tin tác giả đúng.
- [ ] Đã quan sát được số truy vấn của resolver đơn lẻ và xác nhận mẫu N+1.
- [ ] `@BatchMapping` được liên kết đúng với `Book.author`.
- [ ] Service thực hiện truy vấn theo tập ID và loại ID trùng.
- [ ] Kết quả map gắn đúng tác giả với từng sách, không phụ thuộc thứ tự database.
- [ ] Trường hợp ID null, ID thiếu và danh sách rỗng được xử lý rõ ràng.
- [ ] Tenant và authorization được áp dụng trong batch service.
- [ ] Kiểm thử xác nhận response và số lần gọi backend.
- [ ] Đã đo lại SQL count, batch size và latency với cùng query shape.

## Câu hỏi tự kiểm tra

**Vì sao `@BatchMapping` không tự sửa N+1 nếu service vẫn gọi `findById` cho từng phần tử?** Vì annotation chỉ gom các source object vào một lần gọi batch resolver; phần truy cập dữ liệu vẫn do code của ứng dụng quyết định. Nếu code tiếp tục lặp và truy vấn đơn, N+1 chỉ chuyển vào bên trong batch method.

**Vì sao ví dụ trả về `Map<Book, Author>` thay vì `List<Author>`?** Map liên kết trực tiếp mỗi source `Book` với kết quả tương ứng. Truy vấn `IN` không đảm bảo thứ tự bản ghi trả về, nên không thể mặc định vị trí tác giả trong list khớp với vị trí sách.

**DataLoader có phải cache dùng chung cho mọi request không?** Không. DataLoader được dùng để gom và quản lý việc nạp dữ liệu trong quá trình thực thi GraphQL. Không xem nó là cache phân tán hoặc cơ chế chia sẻ dữ liệu giữa người dùng.

**Làm sao chứng minh N+1 đã được sửa?** Dùng cùng query shape và dữ liệu đại diện, đo số SQL/lời gọi backend trước và sau, kiểm tra batch size và xác nhận response vẫn đúng. Latency giảm trong một lần chạy đơn lẻ chưa đủ chứng minh.

Khi hoàn thành, bạn cần thấy số lần truy cập tác giả tăng theo số batch hợp lý thay vì tăng theo từng sách, đồng thời mọi field vẫn tuân thủ schema, tenant và quyền truy cập.
