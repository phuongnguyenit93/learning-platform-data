# Batch mapping bằng Mono

## 1. Vì sao cần Batch Mapping?

Trong GraphQL, một query có thể lấy danh sách object rồi tiếp tục chọn các field quan hệ của từng object. Ví dụ client lấy 30 quyển sách và yêu cầu thêm thông tin tác giả:

```graphql
query BookCatalog {
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

Resolver `Query.books` có thể tải 30 quyển sách bằng một truy vấn. Nếu field `Book.author` gọi repository riêng cho từng quyển sách, server có thể thực hiện thêm 30 truy vấn tác giả. Đây là vấn đề N+1.

Spring for GraphQL cung cấp `@BatchMapping` để gom các source object của cùng một field vào một lần xử lý batch. Khi dùng với Reactor, phương thức có thể trả về `Mono<Map<Source, Target>>` hoặc `Mono<List<Target>>`. Cách này cho phép ứng dụng thực hiện một truy vấn lấy nhiều dữ liệu quan hệ rồi trả kết quả cho GraphQL theo đúng source object.

`Mono` đại diện cho một kết quả bất đồng bộ có thể phát ra tối đa một giá trị. Trong Batch Mapping, giá trị đó thường là toàn bộ map hoặc list của một batch, chứ không phải một `Mono` riêng cho từng parent object.

## 2. `@BatchMapping` hoạt động như thế nào?

Với field lồng nhau, Spring for GraphQL thường có thể gọi một `@SchemaMapping` cho mỗi source object. `@BatchMapping` thay thế cách gọi riêng lẻ đó bằng một batch function:

1. GraphQL phân giải field cha, ví dụ `Query.books`, và nhận danh sách `Book`.
2. Các lần yêu cầu field `Book.author` được gom qua DataLoader do Spring đăng ký.
3. Khi batch được dispatch, Spring gọi phương thức `@BatchMapping` với danh sách các `Book` cần phân giải.
4. Phương thức thực hiện truy vấn theo lô và trả về một `Mono` chứa map hoặc list kết quả.
5. Spring/DataLoader ghép từng kết quả với source object tương ứng và tiếp tục hoàn thiện GraphQL response.

```mermaid
flowchart TD
    A[Query books] --> B[Danh sách Book]
    B --> C[Các yêu cầu Book.author]
    C --> D[DataLoader gom source objects]
    D --> E[@BatchMapping nhận List<Book>]
    E --> F[Service tải nhiều Author]
    F --> G[Mono phát Map hoặc List]
    G --> H[Ghép Author với từng Book]
    H --> I[GraphQL response]
```

Điểm quan trọng là phương thức batch nhận nhiều parent object trong cùng một lần gọi. Vì vậy, truy vấn backend có thể dùng một câu `WHERE id IN (...)` hoặc cơ chế bulk lookup thay cho một truy vấn cho mỗi parent.

## 3. Khai báo schema và mô hình Java

Giả sử mỗi sách tham chiếu đến một tác giả bằng `authorId`:

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

Field `Book.author` nullable vì ví dụ cho phép sách chưa có tác giả hoặc dữ liệu tác giả không còn tồn tại. Nếu nghiệp vụ bảo đảm quan hệ luôn hợp lệ, có thể khai báo `Author!`; khi đó batch mapping phải luôn cung cấp một tác giả hợp lệ cho từng sách.

Mô hình Java minh họa:

```java
public record Book(
    String id,
    String title,
    String authorId) {
}

public record Author(
    String id,
    String name) {
}
```

Record được dùng để ví dụ ngắn gọn. Trong ứng dụng thực tế, `Book` và `Author` có thể là domain object hoặc DTO được tạo từ persistence entity.

## 4. Viết Batch Mapping trả về `Mono<Map<Book, Author>>`

Khi service có thể tải tác giả theo một tập ID, cách rõ ràng là nhận danh sách sách, thu thập các `authorId` khác null, tải tất cả tác giả rồi lập map từ từng `Book` sang `Author`:

```java
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.graphql.data.method.annotation.BatchMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class BookBatchController {

    private final AuthorQueryService authorQueryService;

    public BookBatchController(AuthorQueryService authorQueryService) {
        this.authorQueryService = authorQueryService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Mono<Map<Book, Author>> author(List<Book> books) {
        Set<String> authorIds = books.stream()
            .map(Book::authorId)
            .filter(id -> id != null)
            .collect(Collectors.toSet());

        return authorQueryService.findAllByIds(authorIds)
            .map(authorsById -> books.stream()
                .filter(book -> book.authorId() != null
                    && authorsById.containsKey(book.authorId()))
                .collect(Collectors.toMap(
                    Function.identity(),
                    book -> authorsById.get(book.authorId())
                )));
    }
}
```

Service có thể trả `Mono<Map<String, Author>>`:

```java
public interface AuthorQueryService {
    Mono<Map<String, Author>> findAllByIds(Set<String> authorIds);
}
```

Phương thức `author` trả `Mono<Map<Book, Author>>`. Key của map là source object `Book`; value là kết quả cho field `author`. Spring for GraphQL sử dụng quan hệ key-value để gán đúng tác giả cho từng quyển sách.

Trong ví dụ, nếu một sách không có `authorId` hoặc không tìm thấy tác giả tương ứng, sách đó không xuất hiện trong map. Với mapped batch loading, key không có entry sẽ nhận kết quả null. Điều này phù hợp với SDL `author: Author` nullable.

## 5. Vì sao `Mono` chứa cả batch?

Chữ ký sau có nghĩa là một lần xử lý batch phát ra một map khi dữ liệu sẵn sàng:

```java
Mono<Map<Book, Author>> author(List<Book> books)
```

Các thành phần có ý nghĩa như sau:

- `List<Book>`: tất cả source object cần phân giải trong batch hiện tại.
- `Mono<...>`: kết quả được cung cấp bất đồng bộ và chỉ phát tối đa một lần.
- `Map<Book, Author>`: kết quả cho nhiều source object, được ghép theo key.

Không viết một phương thức trả `Mono<Author>` khi nhận `List<Book>` nếu mục tiêu là cung cấp kết quả cho toàn bộ batch. Một `Mono<Author>` chỉ biểu diễn một giá trị đơn, không đủ để ánh xạ quan hệ của nhiều sách.

Tương tự, không tự subscribe trong controller:

```java
// Không nên: tự subscribe làm tách luồng xử lý khỏi GraphQL execution.
Mono<Map<Book, Author>> result = authorQueryService.findAllByIds(authorIds);
result.subscribe();
```

Hãy trả trực tiếp publisher cho Spring for GraphQL:

```java
return authorQueryService.findAllByIds(authorIds)
    .map(authorsById -> mapBooksToAuthors(books, authorsById));
```

Spring for GraphQL và Reactor quản lý việc subscribe và phối hợp kết quả với GraphQL execution. Việc gọi `subscribe()` thủ công có thể khiến response được hoàn thành trước khi dữ liệu sẵn sàng và làm mất đường truyền lỗi.

## 6. Trả về `Mono<List<Author>>` khi muốn ghép theo thứ tự

Ngoài map, Batch Mapping có thể trả về một list kết quả. Trong trường hợp này, list phải có cùng số lượng và thứ tự với danh sách source object đầu vào.

Ví dụ:

```java
@BatchMapping(typeName = "Book", field = "author")
public Mono<List<Author>> author(List<Book> books) {
    List<String> authorIds = books.stream()
        .map(Book::authorId)
        .toList();

    return authorQueryService.findAllByIdsInOrder(authorIds);
}
```

Service `findAllByIdsInOrder` phải trả về một `List<Author>` có cùng số phần tử với `books`, trong đó phần tử ở vị trí `i` là tác giả của `books.get(i)`. Nếu `authorId` null hoặc một tác giả không tồn tại, phần tử tương ứng cần là `null` nếu field nullable. Service phải giữ vị trí của những key thiếu thay vì loại chúng khỏi list.

Ví dụ source list:

```text
books:   [Book-A, Book-B, Book-C]
authors: [Author-A, null, Author-C]
```

GraphQL ghép theo vị trí: `Book-A` nhận `Author-A`, `Book-B` nhận null và `Book-C` nhận `Author-C`.

Không trả list chỉ chứa các tác giả tìm thấy nếu có key bị thiếu. Ví dụ `[Author-A, Author-C]` có hai phần tử sẽ không còn tương ứng với ba source object. Nếu backend không giữ được thứ tự, `Mono<Map<Book, Author>>` thường an toàn và dễ kiểm tra hơn.

## 7. Chọn Map hay List?

| Tiêu chí | `Mono<Map<Book, Author>>` | `Mono<List<Author>>` |
| --- | --- | --- |
| Cách ghép | Theo source object làm key | Theo vị trí trong list |
| Thứ tự backend | Không cần giữ thứ tự nếu map key chính xác | Bắt buộc khôi phục đúng thứ tự |
| Dữ liệu thiếu | Bỏ key khỏi map để kết quả tương ứng là null | Đặt null tại đúng vị trí |
| Rủi ro chính | Key map không khớp source object | Sai thứ tự hoặc sai số lượng phần tử |
| Phù hợp | Repository trả map theo ID hoặc kết quả không có thứ tự | Backend đã trả đúng thứ tự theo danh sách đầu vào |

Ưu tiên Map khi truy vấn backend bằng `IN (...)`, vì database thường không cam kết thứ tự kết quả nếu không có `ORDER BY`. Chọn List khi service có thể bảo đảm kết quả theo đúng thứ tự đầu vào và việc ánh xạ theo vị trí được kiểm thử rõ ràng.

## 8. Map key phải khớp với source object

Với `Mono<Map<Book, Author>>`, key trong map phải tương ứng với những `Book` đã được truyền vào phương thức batch. Java map sử dụng `equals` và `hashCode` để tra key, vì vậy cần hiểu cách domain object định nghĩa hai phương thức này.

Java record tự sinh `equals` và `hashCode` dựa trên các thành phần record. Nếu dùng entity JPA, không nên tùy tiện đưa mọi field mutable vào `equals` và `hashCode`, vì thay đổi field sau khi thêm entity vào map có thể làm hỏng khả năng tra cứu. Hãy chọn chiến lược equality ổn định theo domain.

Ví dụ lập map trực tiếp từ đúng source instances:

```java
Map<Book, Author> result = new LinkedHashMap<>();

for (Book book : books) {
    Author author = authorsById.get(book.authorId());
    if (author != null) {
        result.put(book, author);
    }
}
```

Ở đây map dùng chính các object `Book` được nhận trong batch. Với source object là entity có proxy hoặc equality phức tạp, cần kiểm thử việc tra key và cân nhắc dùng một DTO/record ổn định làm source của GraphQL.

## 9. Xử lý batch rỗng và dữ liệu không tìm thấy

Một batch có thể không có source object hoặc backend không tìm thấy dữ liệu cho bất kỳ key nào. Khi đó, kết quả đúng kiểu vẫn là một map hoặc list rỗng:

```java
if (books.isEmpty()) {
    return Mono.just(Map.of());
}
```

Với service reactive, cũng có thể để service nhận tập ID rỗng và trả `Mono.just(Map.of())`. Không dùng `Mono.empty()` để biểu diễn một batch không có kết quả. `Mono.empty()` có nghĩa publisher hoàn tất mà không phát ra giá trị batch; đó không phải cùng hợp đồng với một map rỗng.

Với một số key thiếu dữ liệu:

- Nếu field trong SDL nullable, bỏ key khỏi map để kết quả field tương ứng là null.
- Nếu field non-null, missing value sẽ gây lỗi GraphQL và null propagation.
- Nếu dữ liệu thiếu là vi phạm toàn vẹn, có thể phát sinh lỗi nghiệp vụ rõ ràng thay vì âm thầm trả map thiếu key.
- Nếu `authorId` của parent là null, không đưa null vào tập key truy vấn.

Không chuyển lỗi database hoặc lỗi mạng thành `Mono.just(Map.of())`. Map rỗng biểu thị truy vấn thành công nhưng không tìm thấy bản ghi; lỗi hạ tầng cần được truyền dưới dạng error signal để GraphQL error handling xử lý đúng.

## 10. Dùng reactive repository với Mono

Trường hợp tốt nhất là service và repository đã hỗ trợ reactive. Khi đó, phương thức batch có thể compose publisher mà không blocking:

```java
public interface ReactiveAuthorRepository {
    Mono<List<Author>> findAllByIdIn(Set<String> ids);
}
```

Service chuyển list kết quả thành map theo ID:

```java
@Service
public class AuthorQueryService {

    private final ReactiveAuthorRepository repository;

    public AuthorQueryService(ReactiveAuthorRepository repository) {
        this.repository = repository;
    }

    public Mono<Map<String, Author>> findAllByIds(Set<String> ids) {
        if (ids.isEmpty()) {
            return Mono.just(Map.of());
        }

        return repository.findAllByIdIn(ids)
            .map(authors -> authors.stream()
                .collect(Collectors.toMap(
                    Author::id,
                    Function.identity()
                )));
    }
}
```

Batch mapping compose kết quả:

```java
@BatchMapping(typeName = "Book", field = "author")
public Mono<Map<Book, Author>> author(List<Book> books) {
    Set<String> ids = books.stream()
        .map(Book::authorId)
        .filter(Objects::nonNull)
        .collect(Collectors.toSet());

    return authorQueryService.findAllByIds(ids)
        .map(authorsById -> toBookAuthorMap(books, authorsById));
}
```

Không gọi `.block()` trong phương thức Batch Mapping để chờ reactive repository. Làm như vậy sẽ chặn thread và loại bỏ lợi ích của reactive pipeline; trong một số execution context có thể gây deadlock hoặc giảm thông lượng.

## 11. Khi service dùng JPA/JDBC blocking

Không phải dự án Spring for GraphQL nào cũng dùng reactive database. Nếu service dùng Spring Data JPA hoặc JDBC, truy vấn repository là blocking. Việc bọc nó trong `Mono.fromCallable` chỉ tạo publisher trì hoãn thực thi, không biến lời gọi thành non-blocking.

Nếu cần trả `Mono` và đang chạy trong reactive execution, có thể offload công việc blocking sang bounded elastic scheduler:

```java
return Mono.fromCallable(() -> authorQueryService.findAllByIds(ids))
    .subscribeOn(Schedulers.boundedElastic());
```

Hãy cân nhắc thread model của ứng dụng. Với stack MVC và repository blocking, có thể dùng phương thức batch đồng bộ trả `Map<Book, Author>` nếu phù hợp với cấu hình thực thi. Với stack reactive, không chạy JPA/JDBC trực tiếp trên event-loop thread.

Không dùng `.block()` để biến reactive service thành kết quả đồng bộ trong resolver. Chọn một cách xử lý nhất quán với công nghệ truy cập dữ liệu và cấu hình GraphQL của ứng dụng.

## 12. `@BatchMapping` tự tích hợp DataLoader

`@BatchMapping` là shortcut của Spring for GraphQL cho việc đăng ký batch loader và data fetcher cho một field. Ứng dụng không cần tự tạo `DataLoader` hoặc đăng ký `BatchLoaderRegistry` cho trường hợp batch đơn giản này.

Spring dùng source object làm key của batch loader. Khi phương thức trả Map, map phải ánh xạ source object sang giá trị field. Khi phương thức trả List, kết quả phải giữ đúng thứ tự source object.

Do đó, không cần viết thêm một `@SchemaMapping` cho cùng field `Book.author` khi đã có `@BatchMapping`. Hai phương thức cùng đăng ký một field có thể gây xung đột mapping hoặc khiến ownership của resolver không rõ ràng.

Nếu cần một DataLoader theo ID được chia sẻ bởi nhiều field khác nhau, cần custom key, custom name hoặc `DataLoaderOptions`, hãy cân nhắc đăng ký qua `BatchLoaderRegistry` và để `@SchemaMapping` gọi `DataLoader.load`. Chọn một cơ chế cho mỗi cặp type/field.

## 13. Điều chỉnh kích thước batch

Một query có thể yêu cầu rất nhiều source object. Batch quá lớn có thể tạo truy vấn `IN` với hàng nghìn tham số, tăng bộ nhớ và làm database chịu tải cao. Spring for GraphQL hỗ trợ giới hạn kích thước batch của `@BatchMapping` qua thuộc tính `maxBatchSize` ở các phiên bản có hỗ trợ:

```java
@BatchMapping(
    typeName = "Book",
    field = "author",
    maxBatchSize = 100
)
public Mono<Map<Book, Author>> author(List<Book> books) {
    // Tải tác giả cho tối đa một batch theo cấu hình.
    return loadAuthors(books);
}
```

Khi số source object vượt giới hạn, DataLoader có thể chia thành nhiều batch. Vì vậy, không nên giả định một operation lớn luôn chỉ gọi phương thức batch đúng một lần. Hãy chọn giới hạn dựa trên số bind parameter, kích thước response, thời gian truy vấn và năng lực database.

Nếu phiên bản Spring for GraphQL đang dùng chưa có thuộc tính `maxBatchSize` trên `@BatchMapping`, hãy kiểm tra API của phiên bản đó và cấu hình batch size qua cơ chế DataLoader tương ứng. Không sao chép thuộc tính từ tài liệu của phiên bản khác mà chưa xác nhận dependency thực tế.

## 14. Kiểm thử Batch Mapping bằng `GraphQlTester`

Kiểm thử nên xác nhận response đúng và batch function thực sự gom nhiều source object. Ví dụ operation:

```java
@SpringBootTest
@AutoConfigureHttpGraphQlTester
class BookBatchMappingTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void resolvesAuthorsForBooks() {
        graphQlTester.document("""
            query {
                books {
                    id
                    title
                    author {
                        id
                        name
                    }
                }
            }
            """)
            .execute()
            .path("books[0].author.name")
            .entity(String.class)
            .isEqualTo("Nguyen An");
    }
}
```

Ví dụ giả định test context có dữ liệu fixture và service trả về tác giả `Nguyen An` cho quyển sách đầu tiên.

Để xác nhận batching thay vì chỉ xác nhận response, dùng spy hoặc counter cho service:

- Chuẩn bị nhiều sách có cùng và khác `authorId`.
- Gửi một query lấy danh sách và field `author`.
- Xác nhận service được gọi với tập ID đã gom, thay vì một lần cho mỗi sách.
- Nếu batch size được giới hạn, xác nhận số lần gọi tương ứng với các batch thực tế.
- Kiểm tra thứ tự và quan hệ source-target không bị tráo.

Các trường hợp cần có:

- Danh sách source rỗng.
- Tất cả key đều tìm thấy dữ liệu.
- Một vài key không có dữ liệu.
- Parent có key null.
- Backend phát sinh lỗi.
- Field nullable và non-null phản ứng đúng khi thiếu kết quả.
- Batch bị chia do `maxBatchSize`.
- Publisher bị hủy hoặc request kết thúc trước khi hoàn tất nếu ứng dụng có tình huống cancellation cần xử lý.

## 15. Các lỗi thường gặp khi dùng Mono trong Batch Mapping

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Field không được phân giải theo batch | Tên type/field của `@BatchMapping` không khớp SDL | Khai báo rõ `typeName` và `field` |
| DataFetcher bị đăng ký trùng | Cùng field có cả `@BatchMapping` và `@SchemaMapping` | Chọn một mapping làm chủ field |
| Field luôn null | Map dùng key khác source object hoặc thiếu entry | Dùng đúng source object làm key và kiểm tra map |
| Kết quả bị gán nhầm parent | Trả list không đúng thứ tự hoặc số lượng | Dùng map hoặc sắp xếp list theo đúng source order |
| Query không hoàn tất | Publisher không phát giá trị hoặc bị block | Trả `Mono` phát map/list và không gọi subscribe/block thủ công |
| Batch rỗng bị lỗi | Trả `Mono.empty()` thay cho map/list rỗng | Trả `Mono.just(Map.of())` hoặc `Mono.just(List.of())` |
| Thread bị chặn | Dùng JPA/JDBC blocking trên reactive thread | Dùng stack đồng bộ phù hợp hoặc offload blocking sang scheduler |
| Database vẫn bị gọi nhiều lần | Batch function tự gọi repository trong vòng lặp | Dùng một truy vấn bulk theo tập key |
| Field nullable trả lỗi | SDL khai báo non-null hoặc lỗi backend bị chuyển sai | Kiểm tra nullability và phân biệt missing data với infrastructure error |
| Batch quá lớn | Không giới hạn số source object | Cấu hình `maxBatchSize` nếu phiên bản hỗ trợ và phân trang query cha |

## 16. Checklist triển khai Batch Mapping bằng Mono

- [ ] Xác định field quan hệ có nguy cơ N+1.
- [ ] Khai báo đúng source type và field trong `@BatchMapping`.
- [ ] Phương thức nhận `List<Source>` và trả `Mono<Map<Source, Target>>` hoặc `Mono<List<Target>>`.
- [ ] Nếu trả Map, key phải tương ứng với source object và equality ổn định.
- [ ] Nếu trả List, số lượng và thứ tự phải khớp danh sách source đầu vào.
- [ ] Trả map/list rỗng bằng `Mono.just(...)` khi không có kết quả batch.
- [ ] Không dùng `Mono.empty()` để biểu diễn collection không có phần tử.
- [ ] Không gọi `subscribe()` hoặc `block()` trong resolver.
- [ ] Không chạy JPA/JDBC blocking trực tiếp trên reactive event-loop.
- [ ] Xử lý missing key phù hợp với nullability trong SDL.
- [ ] Không đăng ký thêm resolver khác cho cùng field.
- [ ] Giới hạn batch size và phân trang field cha khi cần.
- [ ] Kiểm thử response, mapping key, thứ tự và số lần gọi backend.

## Kết luận

`@BatchMapping` kết hợp `Mono` cho phép Spring for GraphQL xử lý nhiều source object trong một batch và trả kết quả bất đồng bộ. Với `Mono<Map<Source, Target>>`, mỗi source object được ghép với giá trị thông qua key; với `Mono<List<Target>>`, list phải giữ đúng số lượng và thứ tự của source list.

Hãy dùng Map khi backend trả dữ liệu theo key và thứ tự không được bảo đảm. Dùng List khi service có thể duy trì thứ tự tương ứng. Trả publisher cho Spring quản lý, không tự subscribe hoặc block; phân biệt dữ liệu thiếu với lỗi hạ tầng, chọn nullability đúng trong SDL và kiểm thử số lần truy vấn để xác nhận N+1 đã được giảm. Với các batch lớn, giới hạn batch size và phân trang query cha để giữ hiệu năng ổn định.

## Tài liệu tham khảo

- [Spring for GraphQL — Annotated Controllers: Batch Mapping](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.schema-mapping.batch-mapping)
- [Spring for GraphQL — Request Execution: Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html#execution.graphql-datafetcher.batch-loading)
- [Project Reactor — Mono](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
