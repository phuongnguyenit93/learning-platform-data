# `Mono` trong Spring for GraphQL

`Mono<T>` là kiểu reactive của Project Reactor, biểu diễn một tác vụ bất đồng bộ có thể phát ra tối đa một giá trị kiểu `T`, hoàn tất mà không có giá trị hoặc kết thúc bằng lỗi. Trong Spring for GraphQL, controller có thể trả về `Mono<T>` để cung cấp dữ liệu cho field GraphQL mà không cần chặn thread để chờ kết quả.

Điều này phù hợp với các query và mutation cần gọi database reactive, service khác hoặc nhiều nguồn dữ liệu bất đồng bộ. GraphQL xử lý giá trị, trạng thái không có giá trị hoặc tín hiệu lỗi của publisher để hoàn thiện response; `Mono` mô tả cách kết quả đó được cung cấp theo thời gian.

## 1. `Mono<T>` là gì?

`Mono<T>` thuộc Project Reactor, trong package `reactor.core.publisher`. Một `Mono` có ba dạng kết quả chính:

| Kết quả | Ý nghĩa |
|---|---|
| `Mono.just(value)` | Phát ra đúng một giá trị rồi hoàn tất. |
| `Mono.empty()` | Hoàn tất mà không phát ra giá trị. |
| `Mono.error(exception)` | Kết thúc bằng lỗi. |

Ví dụ:

```java
Mono<Book> found = Mono.just(new Book("book-01", "GraphQL Basics"));
Mono<Book> missing = Mono.empty();
Mono<Book> failed = Mono.error(new IllegalStateException("Database unavailable"));
```

`Mono` là một `Publisher` theo Reactive Streams. Nhiều `Mono` là lazy: pipeline chỉ thực thi khi có subscriber. Trong một GraphQL request, Spring for GraphQL quản lý việc thực thi publisher và sử dụng tín hiệu của nó để tiếp tục phân giải field.

Một `Mono` không thể phát ra `null`. `Mono.just(null)` là không hợp lệ. Nếu có một giá trị Java có thể `null`, dùng `Mono.justOrEmpty(value)` để biến `null` thành `Mono.empty()`.

## 2. Dùng `Mono` làm kiểu trả về của `@QueryMapping`

Giả sử GraphQL schema khai báo:

```graphql
type Query {
    bookById(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
```

Service sử dụng repository reactive:

```java
@Service
class BookService {

    private final BookRepository bookRepository;

    BookService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    Mono<Book> findById(String id) {
        return bookRepository.findById(id);
    }
}
```

Controller trả trực tiếp `Mono<Book>`:

```java
@Controller
class BookController {

    private final BookService bookService;

    BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    Mono<Book> bookById(@Argument("id") String id) {
        return bookService.findById(id);
    }
}
```

Khi client gửi:

```graphql
query {
    bookById(id: "book-01") {
        id
        title
    }
}
```

Spring for GraphQL xử lý `Mono<Book>` như kết quả bất đồng bộ của field `Query.bookById`. Khi `Mono` phát ra `Book`, GraphQL tiếp tục phân giải các field `id` và `title` theo selection set. Controller không cần tự gọi `subscribe()` hoặc chờ kết quả bằng `block()`.

Kiểu Java `Mono<Book>` không xuất hiện trong SDL. Schema vẫn khai báo kiểu GraphQL là `Book`; reactive publisher chỉ là cách server cung cấp giá trị cho field.

## 3. Dùng `Mono` với `@MutationMapping`

Mutation cũng có thể trả về `Mono<T>` khi thao tác cần thực hiện bất đồng bộ:

```graphql
input CreateBookInput {
    title: String!
}

type Mutation {
    createBook(input: CreateBookInput!): Book!
}
```

```java
@MutationMapping
Mono<Book> createBook(@Argument("input") CreateBookInput input) {
    return bookService.create(input);
}
```

Service có thể kiểm tra dữ liệu, lưu bản ghi qua reactive repository và phát ra object vừa tạo. GraphQL chỉ hoàn thiện response sau khi publisher phát ra kết quả hoặc kết thúc.

Nếu mutation chỉ thực hiện side effect, chẳng hạn xóa một bản ghi, không nên để một field GraphQL Non-null nhận `Mono<Void>` rồi mong nó tự tạo ra giá trị. `Void` không phải output type GraphQL và `Mono<Void>` hoàn tất không phát ra giá trị. Hãy thiết kế kiểu trả về có ý nghĩa, ví dụ:

```graphql
type DeleteBookPayload {
    deletedId: ID!
}

type Mutation {
    deleteBook(id: ID!): DeleteBookPayload!
}
```

```java
public record DeleteBookPayload(String deletedId) {}

@Controller
class BookDeleteController {

    private final BookService bookService;

    BookDeleteController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    Mono<DeleteBookPayload> deleteBook(@Argument("id") String id) {
        return bookService.deleteById(id)
            .thenReturn(new DeleteBookPayload(id));
    }
}
```

Giả sử `bookService.deleteById(id)` trả về `Mono<Void>`. `thenReturn` đợi thao tác xóa hoàn tất rồi phát ra payload. Nếu thao tác xóa phát sinh lỗi, lỗi tiếp tục đi trong reactive chain và được xử lý theo cơ chế lỗi GraphQL của ứng dụng.

## 4. Phân biệt `map` và `flatMap`

Khi làm việc với `Mono`, hai toán tử thường dùng là `map` và `flatMap`:

- `map` biến đổi giá trị đồng bộ và trả về một giá trị mới.
- `flatMap` gọi một hàm trả về publisher khác rồi nối kết quả vào pipeline, tránh tạo `Mono<Mono<T>>`.

Ví dụ dùng `map` để chuyển entity sang DTO:

```java
Mono<BookView> findBookView(String id) {
    return bookRepository.findById(id)
        .map(book -> new BookView(book.getId(), book.getTitle()));
}
```

Ví dụ dùng `flatMap` khi cần gọi tiếp một service bất đồng bộ:

```java
Mono<BookDetails> findBookDetails(String id) {
    return bookRepository.findById(id)
        .flatMap(book -> authorRepository.findById(book.getAuthorId())
            .map(author -> new BookDetails(book, author)));
}
```

Nếu dùng `map` với hàm trả về `Mono<Author>`, kết quả sẽ là `Mono<Mono<Author>>`. `flatMap` làm phẳng publisher lồng nhau và giữ pipeline reactive.

## 5. Kết hợp nhiều nguồn dữ liệu bằng `Mono.zip`

Khi một field cần dữ liệu từ nhiều nguồn độc lập, có thể dùng `Mono.zip` để kết hợp các kết quả:

```java
Mono<BookDashboard> dashboard(String bookId) {
    Mono<Book> book = bookRepository.findById(bookId);
    Mono<List<Review>> reviews = reviewRepository.findByBookId(bookId).collectList();
    Mono<Author> author = authorRepository.findByBookId(bookId);

    return Mono.zip(book, reviews, author)
        .map(tuple -> new BookDashboard(
            tuple.getT1(),
            tuple.getT2(),
            tuple.getT3()
        ));
}
```

`zip` phối hợp các publisher và phát ra kết quả khi mỗi nguồn cần thiết đã phát ra một giá trị. Các nguồn có thể được subscribe trong cùng quá trình thực thi; mức độ chạy đồng thời phụ thuộc cách từng nguồn thực thi và scheduler của chúng.

Lưu ý: nếu một nguồn hoàn tất rỗng, `Mono.zip` mặc định không thể tạo tuple đầy đủ và kết quả kết hợp cũng hoàn tất rỗng. Nếu một nguồn là tùy chọn, hãy quy định giá trị thay thế trước khi zip, ví dụ:

```java
Mono<Author> author = authorRepository.findByBookId(bookId)
    .defaultIfEmpty(Author.unknown());
```

Chỉ dùng giá trị thay thế nếu nó có ý nghĩa nghiệp vụ. Không nên biến việc thiếu dữ liệu bắt buộc thành một object giả chỉ để pipeline hoàn tất.

## 6. Xử lý `Mono.empty()` và nullability trong GraphQL

`Mono.empty()` có nghĩa publisher hoàn tất mà không phát ra giá trị. Khi dùng làm kết quả của GraphQL field, nó tương ứng với việc field không có giá trị (`null`). Kết quả này phải phù hợp với nullability đã khai báo trong SDL.

| SDL | Khi `Mono` hoàn tất rỗng |
|---|---|
| `book: Book` | Field có thể nhận `null`; không vi phạm Non-null. |
| `book: Book!` | Vi phạm hợp đồng Non-null; GraphQL tạo execution error và áp dụng null propagation. |
| `books: [Book!]!` với kiểu trả về `Mono<List<Book>>` | Field danh sách không được `null`; phát ra `List.of()` khi không có phần tử. `Mono.empty()` sẽ trở thành `null`, vi phạm Non-null. |

Nếu repository trả về `Flux<Book>`, có thể dùng `collectList()` để tạo `Mono<List<Book>>`. Toán tử này phát ra một list, kể cả khi không có phần tử:

```java
Mono<List<Book>> books() {
    return bookRepository.findAll().collectList();
}
```

Ví dụ, nếu không tìm thấy sách và API muốn trả `null`:

```java
@QueryMapping
Mono<Book> bookById(@Argument("id") String id) {
    return bookService.findById(id);
}
```

Với schema `bookById(id: ID!): Book`, `Mono.empty()` là một kết quả hợp lệ.

Nếu không tìm thấy sách được xem là lỗi nghiệp vụ, có thể chuyển empty thành exception:

```java
@QueryMapping
Mono<Book> requiredBook(@Argument("id") String id) {
    return bookService.findById(id)
        .switchIfEmpty(Mono.error(new BookNotFoundException(id)));
}
```

Exception có thể được ánh xạ thành `GraphQLError` bằng `@GraphQlExceptionHandler` hoặc `DataFetcherExceptionResolver`. Khi field được khai báo Non-null, hãy hiểu rằng lỗi có thể làm `null` lan truyền lên cấp cha.

Không nên dùng `Mono.just(null)`. Nếu một API Java cũ trả về object có thể `null`, có thể chuyển đổi bằng:

```java
Mono<Book> findLegacyBook(String id) {
    return Mono.fromCallable(() -> legacyBookService.findById(id))
        .subscribeOn(Schedulers.boundedElastic());
}
```

`Mono.fromCallable` phát ra giá trị khi callable trả về object khác `null` và hoàn tất rỗng nếu callable trả về `null`. `Schedulers` được import từ `reactor.core.scheduler.Schedulers`. `boundedElastic` phù hợp hơn event-loop scheduler cho tác vụ blocking có giới hạn. Tuy nhiên, đây là giải pháp tương thích khi chưa thể thay thế API blocking; không nên dùng nó để biến toàn bộ ứng dụng thành reactive giả tạo. Cần đặt giới hạn và theo dõi thời gian thực thi của tác vụ.

## 7. Xử lý lỗi trong reactive pipeline

Khi một publisher phát tín hiệu lỗi, các toán tử tiếp theo không nhận được giá trị bình thường. Có thể biến đổi exception hoặc khôi phục bằng một publisher khác.

### `onErrorMap`

Dùng `onErrorMap` để chuyển lỗi kỹ thuật thành exception miền nghiệp vụ:

```java
Mono<Book> findBook(String id) {
    return bookRepository.findById(id)
        .onErrorMap(
            DatabaseUnavailableException.class,
            ex -> new BookLookupException("Cannot load book", ex)
        );
}
```

Exception sau đó có thể được xử lý bởi GraphQL exception handler. Không nên đưa nguyên message kỹ thuật ra client.

### `onErrorResume`

Dùng `onErrorResume` khi có phương án phục hồi hợp lệ:

```java
Mono<BookSummary> summary(String id) {
    return bookService.loadSummary(id)
        .onErrorResume(ExternalCatalogException.class,
            ex -> cacheService.findSummary(id));
}
```

Trong ví dụ, nếu catalog ngoài gặp lỗi, service thử lấy dữ liệu từ cache. Chỉ nên fallback khi dữ liệu thay thế vẫn đáp ứng hợp đồng và quy tắc nghiệp vụ. Không nên bắt mọi exception rồi trả `Mono.empty()` vì như vậy có thể che giấu lỗi hệ thống thành trường hợp “không tìm thấy”.

### `switchIfEmpty` khác `onErrorResume`

Hai toán tử giải quyết hai tín hiệu khác nhau:

| Toán tử | Kích hoạt khi |
|---|---|
| `switchIfEmpty(...)` | Publisher hoàn tất mà không phát ra giá trị. |
| `onErrorResume(...)` | Publisher kết thúc bằng exception. |

Không dùng `switchIfEmpty` để xử lý exception và cũng không dùng `onErrorResume` để thay thế logic cho dữ liệu vắng mặt nếu hai trường hợp có ý nghĩa khác nhau.

## 8. `Mono` là lazy: không gọi `block()` hoặc `subscribe()` trong resolver

Một pipeline Reactor thường chỉ bắt đầu khi có subscriber. Spring for GraphQL nhận `Mono` từ handler và quản lý quá trình subscribe khi thực thi field. Vì vậy, resolver nên trả publisher:

```java
@QueryMapping
Mono<Book> bookById(@Argument("id") String id) {
    return bookService.findById(id);
}
```

Không nên tự subscribe:

```java
@QueryMapping
Mono<Book> bookById(@Argument("id") String id) {
    bookService.findById(id).subscribe();
    return Mono.empty();
}
```

Đoạn mã sai này tạo một subscription riêng, tách khỏi vòng đời GraphQL. GraphQL không nhận được kết quả của truy vấn và có thể trả `null` trước khi tác vụ độc lập hoàn tất; lỗi cũng không đi đúng đường xử lý của GraphQL.

Không nên block:

```java
@QueryMapping
Book bookById(@Argument("id") String id) {
    return bookService.findById(id).block();
}
```

`block()` chặn thread để chờ publisher. Điều này làm mất lợi ích của reactive execution và có thể gây lỗi khi chạy trên thread không cho phép blocking. Hãy trả `Mono<Book>` để framework phối hợp bất đồng bộ.

## 9. Tránh chặn thread trong reactive flow

Trả về `Mono` không đảm bảo toàn bộ công việc bên trong là non-blocking. Nếu pipeline gọi JDBC blocking, HTTP client blocking hoặc thao tác I/O đồng bộ, thread vẫn có thể bị chặn.

Ưu tiên dùng:

- Reactive database driver/repository khi cần truy cập dữ liệu reactive.
- WebClient hoặc client có API reactive cho lời gọi HTTP.
- Các toán tử Reactor để nối các tác vụ bất đồng bộ thay vì chờ bằng `get()`, `join()` hoặc `block()`.

Nếu bắt buộc gọi API blocking, cô lập tác vụ đó trên scheduler dành cho blocking work:

```java
Mono<Book> findFromLegacySystem(String id) {
    return Mono.fromCallable(() -> legacyBookService.findById(id))
        .subscribeOn(Schedulers.boundedElastic());
}
```

`Schedulers` được import từ `reactor.core.scheduler.Schedulers`. `Mono.fromCallable` đã chuyển kết quả `null` thành `Mono.empty()`, nên không cần bọc thêm bằng `Mono.justOrEmpty`. `boundedElastic` phù hợp hơn event-loop scheduler cho tác vụ blocking có giới hạn. Tuy nhiên, đây là giải pháp tương thích khi chưa thể thay thế API blocking; không nên dùng nó để biến toàn bộ ứng dụng thành reactive giả tạo. Cần đặt giới hạn và theo dõi thời gian thực thi của tác vụ.

Không nên gọi `subscribeOn` hoặc `publishOn` theo thói quen ở mọi pipeline. Chỉ chỉ định scheduler khi cần kiểm soát nơi chạy một tác vụ cụ thể. Các client reactive thường đã quản lý việc I/O và scheduler nội bộ.

## 10. Kiểm thử `Mono` trong Spring for GraphQL

Có thể dùng `GraphQlTester` để kiểm tra query có resolver trả `Mono`. Mock service phát ra một giá trị bằng `Mono.just`:

```java
@GraphQlTest(BookController.class)
class BookControllerTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @Test
    void returnsBookFromMono() {
        given(bookService.findById("book-01"))
            .willReturn(Mono.just(new Book("book-01", "GraphQL Basics")));

        GraphQlTester.Response response = graphQlTester.document("""
                query {
                    bookById(id: "book-01") {
                        id
                        title
                    }
                }
                """)
            .execute();

        response.path("bookById.id").entity(String.class).isEqualTo("book-01");
        response.path("bookById.title").entity(String.class).isEqualTo("GraphQL Basics");
    }
}
```

Đây là ví dụ minh họa; các import, static import `given`, lớp `Book`, `BookService` và SDL cần có trong test context. Tùy phiên bản Spring Boot, annotation mock bean có thể là `@MockitoBean` hoặc `@MockBean`.

Nên bổ sung kiểm thử cho các tín hiệu còn lại:

- `Mono.empty()` với field nullable: response có giá trị `null` và không có lỗi chỉ vì field rỗng.
- `Mono.empty()` với field Non-null: response có execution error do vi phạm nullability.
- `Mono.error(...)`: exception được ánh xạ thành GraphQL error có mã và path phù hợp.
- `onErrorResume(...)`: fallback chỉ được dùng cho loại lỗi dự kiến.
- Mutation trả `Mono<Payload>`: kiểm tra side effect hoàn tất trước khi payload được trả về.

Ở tầng service, có thể dùng `StepVerifier` để kiểm tra publisher độc lập với GraphQL, chẳng hạn xác minh `Mono.empty()`, giá trị phát ra hoặc exception. Kiểm thử `GraphQlTester` xác nhận thêm cách Spring for GraphQL chuyển tín hiệu reactive thành response GraphQL.

## 11. `Mono` và các kiểu trả về khác

| Kiểu trả về | Ý nghĩa | Trường hợp thường dùng |
|---|---|---|
| `Book` | Một giá trị đồng bộ | Service đồng bộ hoặc dữ liệu đã có sẵn. |
| `Mono<Book>` | 0 hoặc 1 giá trị bất đồng bộ | Tìm một bản ghi, gọi một service reactive. |
| `CompletableFuture<Book>` | Một kết quả bất đồng bộ | Tích hợp API Java async hoặc thư viện dùng Future. |
| `Flux<Book>` | 0 đến nhiều phần tử theo reactive stream | Danh sách dữ liệu reactive hoặc stream, tùy field và loại operation. |
| `Mono<List<Book>>` | Một kết quả chứa cả danh sách | Trả về một collection sau khi truy vấn hoàn tất. |

`Mono<Book>` không có nghĩa là một GraphQL list. Nó biểu diễn một giá trị `Book` hoặc không có giá trị. Nếu schema cần `[Book!]!`, kết quả Java có thể là `Mono<List<Book>>` để phát ra một danh sách hoàn chỉnh. Với subscription hoặc luồng sự kiện, `Flux<T>` thường phù hợp hơn vì có thể phát nhiều phần tử theo thời gian.

Không chọn kiểu reactive chỉ vì nó có vẻ hiện đại. Hãy chọn dựa trên cách service và data source thực sự hoạt động. Nếu mọi tầng đều blocking, bọc chúng trong `Mono` không tự mang lại lợi ích non-blocking.

## 12. Lỗi thường gặp

**Gọi `block()` trong controller.** Thread bị chặn và reactive flow mất lợi ích. Trả publisher trực tiếp cho Spring for GraphQL.

**Tự gọi `subscribe()` trong resolver.** Kết quả tách khỏi GraphQL execution; framework không chờ và không nhận đúng lỗi. Hãy trả `Mono`.

**Dùng `Mono.just(null)`.** Reactor không cho phép phát `null`. Dùng `Mono.empty()` hoặc `Mono.justOrEmpty(value)`.

**Nhầm `Mono.empty()` với `Mono.error(...)`.** Empty là hoàn tất không có giá trị; error là kết thúc thất bại. Chọn tín hiệu theo ý nghĩa nghiệp vụ.

**Không đồng bộ nullability SDL.** Empty được ánh xạ thành `null`; field Non-null sẽ phát sinh execution error và null propagation.

**Bọc một API blocking vào `Mono` rồi cho rằng đã non-blocking.** Phần thân blocking vẫn chặn thread. Dùng client reactive hoặc cô lập tác vụ blocking trên scheduler phù hợp.

**Nuốt mọi lỗi bằng `onErrorResume`.** Fallback thành empty hoặc giá trị mặc định có thể che giấu sự cố. Chỉ phục hồi các lỗi có phương án thay thế rõ ràng.

**Dùng `Mono<Void>` cho field cần giá trị GraphQL.** Hoàn tất rỗng không tạo output. Trả payload hoặc scalar có ý nghĩa sau side effect bằng `thenReturn`.

## Kết luận

`Mono<T>` cho phép resolver Spring for GraphQL cung cấp một giá trị bất đồng bộ hoặc hoàn tất rỗng/lỗi mà không chặn thread chờ kết quả. Dùng `map` cho biến đổi đồng bộ, `flatMap` để nối tác vụ reactive, `zip` để kết hợp nguồn độc lập, `switchIfEmpty` cho trường hợp không có dữ liệu và `onErrorResume` cho phương án phục hồi có chủ đích. Luôn đồng bộ `Mono.empty()` với nullability SDL, tránh `block()`/`subscribe()` trong resolver và kiểm thử cả giá trị, empty lẫn error bằng `GraphQlTester`.

## Tài liệu tham khảo

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [Project Reactor — `Mono` API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
