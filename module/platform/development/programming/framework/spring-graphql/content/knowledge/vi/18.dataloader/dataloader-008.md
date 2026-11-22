# DataLoader method argument trong Spring for GraphQL

Trong Spring for GraphQL, một phương thức `@SchemaMapping` có thể nhận `DataLoader<K, V>` trực tiếp như một method argument. Spring tìm DataLoader đã đăng ký trong request hiện tại, inject vào phương thức và cho phép resolver gọi `load(key)` để lấy dữ liệu liên quan theo cách có thể gom nhiều yêu cầu thành một batch.

Cách này thường được dùng để tải quan hệ từ object cha, chẳng hạn mỗi `Book` có `authorId` và field `Book.author` cần trả về một `Author`. Khi query lấy nhiều sách, mỗi resolver gọi `DataLoader.load(authorId)`. DataLoader gom các key, gọi batch loader và lưu cache trong phạm vi request, giúp giảm truy vấn N+1.

## 1. Vì sao cần DataLoader method argument?

Giả sử schema có các kiểu:

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

Query của client:

```graphql
query {
    books {
        id
        title
        author {
            name
        }
    }
}
```

Nếu resolver `Book.author` gọi repository riêng cho từng sách, một query lấy 100 sách có thể tạo ra một truy vấn lấy danh sách sách và thêm 100 truy vấn lấy tác giả. Đây là vấn đề N+1.

DataLoader cho phép resolver yêu cầu dữ liệu theo từng key mà không phải tải ngay lập tức. Các lời gọi `load()` trong cùng một đợt thực thi được gom lại; batch loader nhận tập key và tải dữ liệu bằng một thao tác phù hợp, ví dụ truy vấn `WHERE id IN (...)`.

Trong Spring for GraphQL, ta đăng ký batch loading function qua `BatchLoaderRegistry`, sau đó khai báo `DataLoader<K, V>` trong chữ ký phương thức `@SchemaMapping`. Spring tự tìm và inject DataLoader phù hợp.

## 2. Luồng hoạt động của DataLoader method argument

Quá trình thường diễn ra theo các bước:

1. Ứng dụng đăng ký batch loading function với `BatchLoaderRegistry`.
2. Khi GraphQL request bắt đầu, Spring tạo các DataLoader tương ứng trong `DataLoaderRegistry` của request đó.
3. Resolver `Query.books` trả về danh sách `Book`.
4. GraphQL gọi resolver `Book.author` cho từng sách. Spring inject cùng DataLoader tương ứng vào mỗi lần gọi.
5. Resolver gọi `loader.load(book.authorId())`. Các key được xếp hàng thay vì tải riêng ngay tại thời điểm gọi.
6. GraphQL dispatch DataLoader; batch loader nhận các key cần tải và truy vấn dữ liệu theo lô.
7. DataLoader hoàn tất các future đã trả về từ `load()`, rồi GraphQL tiếp tục phân giải field `Author.name`.

```text
Query.books
    |
    +-- Book(1, authorId=10) --+
    +-- Book(2, authorId=20) --+--> DataLoader.load(key)
    +-- Book(3, authorId=10) --+          |
                                         v
                              BatchLoaderRegistry
                                         |
                                         v
                              Batch loader nhận keys
                                  {10, 20}
                                         |
                                         v
                              Một lần tải theo lô
                                         |
                                         v
                              Map<id, Author>
                                         |
                                         v
                              Hoàn tất các Future
```

Nếu các key trùng nhau, cache theo request của DataLoader có thể tránh tải lặp lại cùng key. Trong ví dụ trên, hai sách cùng có `authorId = 10` thường chỉ cần một mục tải cho key đó.

## 3. Đăng ký batch loader bằng `BatchLoaderRegistry`

Spring Boot Starter cung cấp bean `BatchLoaderRegistry`. Ta có thể inject bean này vào configuration hoặc component để đăng ký batch loader.

Giả sử các model Java:

```java
public record Book(Long id, String title, Long authorId) {}

public record Author(Long id, String name) {}
```

Service truy cập tác giả bằng tập ID:

```java
@Service
class AuthorService {

    private final AuthorRepository authorRepository;

    AuthorService(AuthorRepository authorRepository) {
        this.authorRepository = authorRepository;
    }

    Flux<Author> findAllByIds(Set<Long> ids) {
        return authorRepository.findAllById(ids);
    }
}
```

Đăng ký mapped batch loader:

```java
@Configuration
class GraphQlDataLoaderConfig {

    GraphQlDataLoaderConfig(
            BatchLoaderRegistry registry,
            AuthorService authorService) {

        registry.forTypePair(Long.class, Author.class)
            .registerMappedBatchLoader((authorIds, environment) ->
                authorService.findAllByIds(authorIds)
                    .collectMap(Author::id)
            );
    }
}
```

`forTypePair(Long.class, Author.class)` khai báo key là `Long` và value là `Author`. `registerMappedBatchLoader` nhận một tập key và trả về `Mono<Map<K, V>>`. Trong ví dụ, repository tải các tác giả theo tập ID rồi `collectMap(Author::id)` tạo map có key là ID tác giả.

Mapped batch loader phù hợp khi một số key có thể không có giá trị tương ứng. Map có thể không chứa key không tìm thấy; DataLoader sẽ trả kết quả không có giá trị cho key đó. Nếu cần giữ thứ tự đầu vào và biểu diễn từng vị trí, có thể dùng `registerBatchLoader` trả về danh sách/Flux theo đúng thứ tự và số lượng key, với `null` tại vị trí không tìm thấy.

Không nên tự tạo `DataLoaderRegistry` cho từng resolver. `BatchLoaderRegistry` là điểm đăng ký trung tâm của Spring for GraphQL; Spring dùng nó để đăng ký DataLoader theo từng request và hỗ trợ chia sẻ `GraphQLContext` cũng như context propagation cho batch loader.

## 4. Nhận `DataLoader` trong `@SchemaMapping`

Sau khi đăng ký batch loader cho cặp `Long` và `Author`, resolver có thể khai báo `DataLoader<Long, Author>` trong method signature:

```java
@Controller
class BookController {

    private final BookService bookService;

    BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    List<Book> books() {
        return bookService.findAll();
    }

    @SchemaMapping(typeName = "Book", field = "author")
    CompletableFuture<Author> author(
            Book book,
            DataLoader<Long, Author> authorLoader) {

        return authorLoader.load(book.authorId());
    }
}
```

Ở đây:

- `Book book` là parent source của field `Book.author`.
- `DataLoader<Long, Author> authorLoader` là DataLoader Spring inject dựa trên kiểu generic.
- `authorLoader.load(book.authorId())` trả về `CompletableFuture<Author>`.
- `@SchemaMapping` trả future đó cho GraphQL; không cần gọi `get()`, `join()` hoặc `block()`.

DataLoader argument resolver của Spring lấy DataLoader từ `DataFetchingEnvironment` của field hiện tại. Với cấu hình mặc định từ `forTypePair`, tên DataLoader được suy ra từ full class name của value type, ở đây là `Author`. Vì vậy, kiểu generic `DataLoader<Long, Author>` thường đủ để Spring tìm đúng loader mà không cần chỉ định tên.

Các import chính trong ví dụ:

```java
import org.dataloader.DataLoader;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.graphql.execution.BatchLoaderRegistry;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.util.Set;
import java.util.concurrent.CompletableFuture;
```

## 5. Cách Spring tìm DataLoader từ method argument

Spring for GraphQL có `DataLoaderMethodArgumentResolver` để giải quyết tham số kiểu `DataLoader`. Việc tìm loader dựa trên các thông tin sau:

1. **Full class name của value type trong generic:** với `DataLoader<Long, Author>`, mặc định key đăng ký dựa trên tên đầy đủ của lớp `Author`.
2. **Tên tham số phương thức:** được dùng làm key dự phòng hoặc khi loader được đăng ký bằng tên tùy chỉnh.

Với `registry.forTypePair(Long.class, Author.class)`, Spring mặc định tạo tên từ value type `Author`. Vì thế, nhiều trường hợp chỉ cần:

```java
@SchemaMapping
CompletableFuture<Author> author(Book book, DataLoader<Long, Author> loader) {
    return loader.load(book.authorId());
}
```

Tên biến `loader` không cần trùng tên lớp `Author` vì Spring có thể xác định loader từ generic value type. Tuy nhiên, generic phải khai báo đúng key và value type tương ứng với đăng ký.

Nếu khai báo `DataLoader<Long, Book>` trong khi loader được đăng ký cho `Author`, Spring sẽ tìm theo value type `Book` và không lấy đúng loader. Hãy kiểm tra cả hai generic type khi gặp lỗi không tìm thấy DataLoader.

## 6. Đặt tên DataLoader tùy chỉnh

Khi cần nhiều loader cùng value type hoặc muốn tên đăng ký thể hiện rõ mục đích, có thể dùng `forName("...")` hoặc gọi `withName("...")` trên registration spec được tạo từ `forTypePair(...)`.

Ví dụ đăng ký tên `authorsById`:

```java
registry.<Long, Author>forName("authorsById")
    .registerMappedBatchLoader((authorIds, environment) ->
        authorService.findAllByIds(authorIds)
            .collectMap(Author::id)
    );
```

Trong `@SchemaMapping`, tên tham số `DataLoader` phải khớp tên đã đăng ký:

```java
@SchemaMapping(typeName = "Book", field = "author")
CompletableFuture<Author> author(
        Book book,
        DataLoader<Long, Author> authorsById) {

    return authorsById.load(book.authorId());
}
```

Ở trường hợp này, `authorsById` là tên tham số được Spring dùng để tìm loader `authorsById`. Nếu đổi tên tham số mà không đổi tên đăng ký, Spring có thể không tìm thấy DataLoader. Khi dùng tên tùy chỉnh, cần bảo đảm tên tham số được giữ lại trong metadata biên dịch Java; cấu hình compiler với tùy chọn `-parameters` giúp Spring đọc được tên tham số.

Nếu không có nhu cầu đặt tên riêng, nên ưu tiên `forTypePair` và generic type mặc định để giảm phụ thuộc vào tên tham số.

## 7. DataLoader trả về kiểu bất đồng bộ

Phương thức `DataLoader.load(key)` trả về `CompletableFuture<V>`. Vì vậy, `@SchemaMapping` có thể trả trực tiếp `CompletableFuture<Author>`:

```java
@SchemaMapping
CompletableFuture<Author> author(Book book, DataLoader<Long, Author> loader) {
    return loader.load(book.authorId());
}
```

Không nên chờ future ngay trong resolver:

```java
@SchemaMapping
Author author(Book book, DataLoader<Long, Author> loader) {
    return loader.load(book.authorId()).join();
}
```

Đoạn thứ hai làm chặn quá trình thực thi và có thể ngăn GraphQL dispatch batch đúng thời điểm. Trả future cho GraphQL để execution engine phối hợp các tác vụ bất đồng bộ.

Có thể biến đổi kết quả của future bằng `thenApply` nếu cần chuyển đổi đồng bộ:

```java
@SchemaMapping
CompletableFuture<AuthorView> author(Book book, DataLoader<Long, Author> loader) {
    return loader.load(book.authorId())
        .thenApply(author -> new AuthorView(author.id(), author.name()));
}
```

Nếu cần gọi thêm một tác vụ bất đồng bộ trả về `CompletionStage`, dùng `thenCompose` để nối future thay vì tạo future lồng nhau. Cần giữ nguyên lỗi trong pipeline để GraphQL xử lý theo cơ chế exception resolution.

## 8. Batching, cache và phạm vi request

DataLoader có hai lợi ích quan trọng:

**Batching:** các lời gọi `load(key)` được gom lại để batch loader xử lý nhiều key trong một lần. Điều này giảm số lần gọi repository hoặc service khi query có nhiều parent object.

**Cache theo request:** DataLoader mặc định cache kết quả theo key trong suốt vòng đời của GraphQL request. Nếu nhiều field cùng yêu cầu một author ID, các lần gọi sau có thể dùng lại kết quả đã tải.

Cache này không phải cache toàn ứng dụng. Request tiếp theo có DataLoader registry và cache riêng. Vì vậy, dữ liệu không tự động được dùng chung giữa người dùng hoặc request khác nhau.

Khi mutation thay đổi một entity rồi tiếp tục đọc entity đó trong cùng request, cần cân nhắc xóa hoặc cập nhật cache DataLoader liên quan bằng các thao tác như `clear(key)` hoặc `prime(key, value)`. Nếu không, DataLoader có thể trả về giá trị đã cache trước mutation trong cùng request.

Nếu dữ liệu phụ thuộc vào người dùng, tenant hoặc quyền truy cập, cần bảo đảm batch loader sử dụng đúng `GraphQLContext`/security context và key/cache không làm trộn các kết quả có phạm vi truy cập khác nhau. Với dữ liệu cần phân biệt theo filter hoặc tenant, có thể phải đưa thông tin đó vào composed key hoặc xử lý theo context phù hợp.

## 9. Khi nào dùng DataLoader method argument và khi nào dùng `@BatchMapping`?

`@BatchMapping` là cách rút gọn cho trường hợp field resolver chỉ đơn giản tải một quan hệ theo danh sách parent object. Ví dụ:

```java
@BatchMapping(typeName = "Book", field = "author")
Mono<Map<Book, Author>> authors(List<Book> books) {
    Set<Long> authorIds = books.stream()
        .map(Book::authorId)
        .collect(Collectors.toSet());

    return authorService.findAllByIds(authorIds)
        .collectMap(Author::id)
        .map(authorsById -> {
            Map<Book, Author> result = new HashMap<>();
            for (Book book : books) {
                Author author = authorsById.get(book.authorId());
                if (author != null) {
                    result.put(book, author);
                }
            }
            return result;
        });
}
```

Với trường hợp đơn giản này, không cần viết `DataLoader` method argument và `BatchLoaderRegistry` thủ công. Spring tạo batch loader và data fetcher cho field tương ứng. Vì `Book` được dùng làm key của map, kiểu `Book` cần có `equals` và `hashCode` ổn định; Java record tự sinh hai phương thức này dựa trên các thành phần record.

DataLoader method argument phù hợp hơn khi resolver cần thông tin riêng của từng lần gọi field, ví dụ:

- `@Argument` để lọc dữ liệu theo từng parent.
- `GraphQLContext`, principal hoặc context cục bộ.
- Nhiều loader hoặc cách nạp dữ liệu phức tạp.
- Cần chủ động gọi `load`, `loadMany`, `clear` hoặc `prime`.
- Muốn tái sử dụng một loader ở nhiều `@SchemaMapping` khác nhau.

Không nên chọn DataLoader thủ công chỉ vì nó tổng quát hơn. Với quan hệ đơn giản, `@BatchMapping` thường ít boilerplate hơn. Khi cần kiểm soát cách tải theo từng field invocation, DataLoader method argument linh hoạt hơn.

## 10. Kiểm thử DataLoader method argument

Kiểm thử nên xác nhận cả dữ liệu trả về và việc batch loader được gọi với tập key mong đợi. Ví dụ test slice:

```java
@GraphQlTest(BookController.class)
@Import(GraphQlDataLoaderConfig.class)
class BookDataLoaderTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @MockitoBean
    AuthorService authorService;

    @Test
    void batchesAuthorsForMultipleBooks() {
        given(bookService.findAll()).willReturn(List.of(
            new Book(1L, "Book A", 10L),
            new Book(2L, "Book B", 20L),
            new Book(3L, "Book C", 10L)
        ));

        given(authorService.findAllByIds(anySet())).willReturn(Flux.just(
            new Author(10L, "Author A"),
            new Author(20L, "Author B")
        ));

        GraphQlTester.Response response = graphQlTester.document("""
                query {
                    books {
                        id
                        author {
                            name
                        }
                    }
                }
                """)
            .execute();

        response.path("books[0].author.name").entity(String.class).isEqualTo("Author A");
        response.path("books[1].author.name").entity(String.class).isEqualTo("Author B");
        response.path("books[2].author.name").entity(String.class).isEqualTo("Author A");

        then(authorService).should(times(1)).findAllByIds(Set.of(10L, 20L));
    }
}
```

Đây là ví dụ minh họa; các import, static import Mockito/BDDMockito, model, service và SDL cần được cung cấp trong test context. `@Import` đưa cấu hình đăng ký batch loader vào test. Tùy phiên bản Spring Boot, annotation mock bean có thể là `@MockitoBean` hoặc `@MockBean`.

Test có ba sách nhưng chỉ hai author ID khác nhau. Kết quả kiểm tra cho thấy cả ba field `author` được phân giải đúng và service batch được gọi một lần với tập key `{10, 20}`. Trong test thực tế, có thể bổ sung trường hợp không tìm thấy tác giả và xác minh field nullable trả `null`.

## 11. Lỗi thường gặp

**Chưa đăng ký batch loader.** Khai báo `DataLoader<K, V>` trong controller không tự tạo loader. Phải đăng ký tương ứng với `BatchLoaderRegistry` trước khi request chạy.

**Generic type không khớp.** `DataLoader<Long, Author>` phải tương ứng với key type và value type đã đăng ký. Đặc biệt, mặc định tên loader được suy ra từ value type.

**Dùng tên tùy chỉnh nhưng tên tham số không khớp.** Với `forName("authorsById")`, tham số `DataLoader` trong method mapping cần có tên `authorsById` để resolver tìm đúng loader.

**Trả về danh sách batch sai thứ tự.** Với `registerBatchLoader`, số lượng và thứ tự kết quả phải khớp danh sách key. Nếu kết quả không có cho một số key, dùng mapped batch loader hoặc trả `null` đúng vị trí.

**Dùng `join()` hoặc `get()` trong resolver.** Chờ future đồng bộ làm mất tính bất đồng bộ và cản trở batching. Trả `CompletableFuture` trực tiếp.

**Tự gọi `dispatch()` trong controller.** GraphQL execution quản lý việc dispatch DataLoader. Resolver chỉ cần gọi `load()` hoặc `loadMany()`.

**Tạo cache dùng chung toàn ứng dụng.** DataLoader được thiết kế với cache theo request. Không giữ một DataLoader singleton trong controller/service để chia sẻ giữa nhiều request.

**Dùng DataLoader cho quan hệ quá đơn giản.** Nếu chỉ cần batch load theo danh sách parent và không cần argument/context riêng, `@BatchMapping` thường gọn hơn.

## Kết luận

DataLoader method argument cho phép Spring for GraphQL inject `DataLoader<K, V>` trực tiếp vào `@SchemaMapping`. Đăng ký batch loading function qua `BatchLoaderRegistry`, để Spring tạo DataLoader theo request, rồi gọi `load(key)` và trả `CompletableFuture<V>` cho GraphQL. Với `forTypePair`, Spring mặc định tìm loader theo full class name của value type; với tên tùy chỉnh, tên tham số cần khớp tên đăng ký. Hiểu rõ batching, cache theo request, kiểu kết quả batch và khác biệt với `@BatchMapping` sẽ giúp giảm N+1 mà vẫn giữ resolver dễ kiểm thử.

## Tài liệu tham khảo

- [Spring for GraphQL — Request Execution: Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers: DataLoader](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL API — `BatchLoaderRegistry`](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/execution/BatchLoaderRegistry.html)
