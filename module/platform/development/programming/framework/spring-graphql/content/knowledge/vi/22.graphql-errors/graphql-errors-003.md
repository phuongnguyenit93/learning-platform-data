# DataFetchingEnvironment

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vai trò của `DataFetchingEnvironment` trong quá trình thực thi một GraphQL field.
- Đọc argument, source object, GraphQLContext, local context và thông tin field hiện tại.
- Dùng selection set để hiểu những field con client yêu cầu.
- Truy cập execution path và metadata cần thiết để tạo GraphQL error chính xác.
- Kết hợp `DataFetchingEnvironment` với `DataFetcherExceptionResolver` và `DataFetcherResult`.
- Truy cập DataLoader khi cần làm việc trực tiếp với GraphQL Java.
- Biết khi nào nên dùng `DataFetchingEnvironment` và khi nào nên ưu tiên `@Argument`, source parameter hoặc `@ContextValue`.

## 1. DataFetchingEnvironment là gì?

`DataFetchingEnvironment` là đối tượng GraphQL Java cung cấp cho một DataFetcher khi GraphQL đang phân giải một field. Nó chứa dữ liệu và metadata của lần thực thi field hiện tại.

Một field resolver thường cần một hoặc nhiều thông tin:

- Argument mà client truyền vào field.
- Source object do field cha trả về.
- GraphQLContext của request.
- Local context được truyền từ field cha.
- Tên field, định nghĩa field và execution path.
- Các field con mà client đã chọn.
- DataLoader registry và một số metadata của operation.

Các thông tin này được tập hợp trong `DataFetchingEnvironment` để DataFetcher có thể lấy đúng dữ liệu theo ngữ cảnh đang thực thi.

Ví dụ, client gửi query:

~~~graphql
query BookDetail($id: ID!) {
  book(id: $id) {
    id
    title
    author {
      name
    }
  }
}
~~~

Khi field `Query.book` chạy, environment chứa argument `id`. Sau khi field cha trả về Book, resolver của `Book.author` nhận Book đó làm source object. Mỗi field có một environment riêng, phản ánh field và nhánh thực thi tương ứng.

Có thể hình dung:

~~~mermaid
flowchart TD
    A[GraphQL operation] --> B[Query.book]
    B --> C[DataFetchingEnvironment]
    C --> D[Arguments]
    C --> E[GraphQLContext]
    C --> F[Field and execution path]
    C --> G[Selection set]
    B --> H[Book source object]
    H --> I[Book.author]
    I --> J[DataFetchingEnvironment của author]
    J --> K[Source = Book]
    J --> L[Arguments / context / path]
~~~

`DataFetchingEnvironment` là API ở tầng GraphQL Java. Spring for GraphQL cho phép method trong annotated controller nhận đối tượng này khi cần truy cập metadata chi tiết hơn các annotation chuyên biệt.

## 2. Nhận DataFetchingEnvironment trong annotated controller

Một method được đánh dấu bằng `@QueryMapping` hoặc `@SchemaMapping` có thể nhận `DataFetchingEnvironment` như một tham số.

Ví dụ SDL:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
}
~~~

Controller:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(DataFetchingEnvironment environment) {
        String id = environment.getArgument("id");
        return bookService.findById(id);
    }
}
~~~

Spring nhận diện tham số `DataFetchingEnvironment` và cung cấp environment của field đang được gọi. Method đọc argument `id` bằng `getArgument("id")`, sau đó chuyển dữ liệu cho service.

Với một argument đơn giản, cách viết ngắn hơn thường là:

~~~java
@QueryMapping
public Book book(@Argument String id) {
    return bookService.findById(id);
}
~~~

Nên ưu tiên `@Argument` khi chỉ cần bind một giá trị. Dùng `DataFetchingEnvironment` khi resolver cần thêm thông tin như field path, selection set, GraphQLContext hoặc source object.

## 3. Đọc argument của field

`getArgument(name)` lấy giá trị argument của field hiện tại sau khi GraphQL đã parse và coercion theo schema.

Ví dụ:

~~~graphql
type Query {
  searchBooks(keyword: String!, first: Int = 20): [Book!]!
}
~~~

DataFetcher:

~~~java
DataFetcher<List<Book>> searchBooksFetcher = environment -> {
    String keyword = environment.getArgument("keyword");
    Integer first = environment.getArgument("first");

    return bookService.search(keyword, first);
};
~~~

Một số API liên quan:

| API | Ý nghĩa |
|---|---|
| `getArgument("name")` | Lấy một argument theo tên |
| `getArguments()` | Lấy map tất cả argument của field |
| `containsArgument("name")` | Kiểm tra argument có được truyền hay không |
| `getVariables()` | Lấy variables của operation |

GraphQL đã kiểm tra kiểu argument theo SDL trước khi gọi DataFetcher. Ví dụ, nếu `first` khai báo là `Int`, giá trị sai kiểu có thể bị từ chối ở bước coercion trước khi resolver chạy.

### Phân biệt omitted và explicit null

Với argument nullable, client có thể bỏ qua argument hoặc truyền rõ ràng `null`. Hai trạng thái có thể mang ý nghĩa khác nhau trong mutation dạng cập nhật một phần.

`containsArgument("subtitle")` kiểm tra key có hiện diện trong map argument sau coercion hay không. Nếu schema khai báo default value, cần tính đến việc giá trị mặc định có thể đã được áp dụng dù client không gửi argument. Khi cần phân biệt chính xác omitted và explicit null trong annotated controller, `ArgumentValue<T>` là lựa chọn rõ ràng hơn.

~~~java
@MutationMapping
public Book updateSubtitle(
        @Argument String id,
        @Argument ArgumentValue<String> subtitle) {

    if (subtitle.isOmitted()) {
        return bookService.findById(id);
    }

    return bookService.updateSubtitle(id, subtitle.value());
}
~~~

Không nên tự suy luận rằng mọi giá trị Java null đều có cùng ý nghĩa. Hãy thiết kế input contract và resolver theo đúng ngữ nghĩa cập nhật.

## 4. Đọc source object của field hiện tại

Source object là giá trị mà field cha trả về và được dùng làm đầu vào cho field con. Trong `DataFetchingEnvironment`, có thể lấy nó bằng `getSource()`.

SDL:

~~~graphql
type Book {
  id: ID!
  author: Author
}

type Author {
  id: ID!
  name: String!
}
~~~

DataFetcher cho `Book.author`:

~~~java
DataFetcher<Author> authorFetcher = environment -> {
    Book book = environment.getSource();
    return authorService.findById(book.getAuthorId());
};
~~~

Trong annotated controller, có thể nhận source object trực tiếp:

~~~java
@SchemaMapping
public Author author(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

Cách nhận source bằng tham số có kiểu cụ thể thường dễ đọc và an toàn kiểu hơn. `getSource()` hữu ích khi đang làm việc trực tiếp với DataFetcher hoặc cần đọc source cùng nhiều metadata khác trong cùng method.

Source object không phải argument. Với field `Book.author`, source là Book; argument nếu có sẽ là dữ liệu client truyền cho chính field `author`.

## 5. GraphQLContext và local context

Environment cung cấp hai loại context có phạm vi khác nhau.

### GraphQLContext

`getGraphQlContext()` trả về context chung của GraphQL request. Context này phù hợp với metadata được chia sẻ trong quá trình thực thi operation, ví dụ:

- Correlation ID hoặc request ID.
- Tenant đã được xác thực.
- Thông tin principal hoặc quyền đã được xác định ở tầng bảo mật.
- Locale hoặc metadata phục vụ logging.

Ví dụ:

~~~java
@QueryMapping
public List<Book> myBooks(DataFetchingEnvironment environment) {
    GraphQLContext context = environment.getGraphQlContext();
    String tenantId = context.get("tenantId");

    return bookService.findByTenant(tenantId);
}
~~~

Giá trị `tenantId` cần được đưa vào GraphQLContext từ một thành phần đáng tin cậy như interceptor hoặc tích hợp bảo mật. Không lấy tenant hoặc user ID tùy ý từ argument rồi dùng làm ranh giới phân quyền.

Trong annotated controller, có thể dùng `@ContextValue` nếu chỉ cần một giá trị context:

~~~java
@QueryMapping
public List<Book> myBooks(
        @ContextValue("tenantId") String tenantId) {
    return bookService.findByTenant(tenantId);
}
~~~

### Local context

`getLocalContext()` đọc context được field cha truyền xuống các field con. Local context phù hợp với dữ liệu chỉ có ý nghĩa trong một nhánh của cây thực thi.

Một DataFetcher có thể trả về `DataFetcherResult` và gắn local context:

~~~java
DataFetcher<DataFetcherResult<Book>> bookFetcher = environment -> {
    Book book = bookService.findById(
            environment.getArgument("id"));

    Map<String, Object> local = Map.of(
            "includeInternalMetadata", false);

    return DataFetcherResult.<Book>newResult()
            .data(book)
            .localContext(local)
            .build();
};
~~~

Field con có thể đọc local context:

~~~java
DataFetcher<String> internalLabelFetcher = environment -> {
    Map<String, Object> local = environment.getLocalContext();

    boolean allowed = Boolean.TRUE.equals(
            local.get("includeInternalMetadata"));

    return allowed ? "Internal" : "Public";
};
~~~

Ví dụ chỉ minh họa cơ chế truyền dữ liệu theo nhánh. Local context không phải cơ chế authorization thay thế Spring Security; quyền truy cập dữ liệu vẫn phải được kiểm tra ở tầng phù hợp.

| Loại dữ liệu | Phạm vi | API |
|---|---|---|
| Source object | Parent object của field hiện tại | `getSource()` |
| GraphQLContext | Toàn bộ GraphQL request | `getGraphQlContext()` |
| Local context | Nhánh cha-con được truyền có chủ đích | `getLocalContext()` |
| Argument | Field hiện tại | `getArgument(...)` |

Tránh dùng context mutable chung để lưu trạng thái của từng field. Nếu dữ liệu chỉ dành cho một nhánh, local context thể hiện phạm vi rõ hơn.

## 6. Đọc thông tin field và execution path

`DataFetchingEnvironment` cung cấp thông tin về field đang được thực thi và vị trí của field trong response.

Các API thường dùng:

| API | Nội dung |
|---|---|
| `getField()` | Field node trong GraphQL document |
| `getFieldDefinition()` | Định nghĩa field trong schema |
| `getExecutionStepInfo()` | Thông tin bước thực thi hiện tại |
| `getExecutionStepInfo().getPath()` | Đường dẫn field trong response |
| `getMergedField()` | Thông tin các field được merge cho cùng response key |
| `getOperationDefinition()` | Định nghĩa operation |
| `getExecutionId()` | ID của lần thực thi |

Ví dụ lấy tên field, alias và path:

~~~java
DataFetcher<Book> bookFetcher = environment -> {
    String fieldName = environment.getField().getName();
    String alias = environment.getField().getAlias();
    String path = environment.getExecutionStepInfo()
            .getPath()
            .toString();

    log.debug(
            "Resolving field={}, alias={}, path={}",
            fieldName, alias, path);

    return bookService.findById(
            environment.getArgument("id"));
};
~~~

Nếu client dùng alias:

~~~graphql
query {
  featured: book(id: "b-01") {
    title
  }
}
~~~

Tên field trong schema vẫn là `book`, còn response key là `featured`. Execution path phản ánh vị trí trong response và có thể chứa alias hoặc chỉ số list. Điều này hữu ích khi ghi log hoặc gắn lỗi vào đúng field.

Không nên dùng tên field hoặc path để quyết định quyền truy cập. Chúng là metadata của operation, không phải danh tính hay bằng chứng người dùng được phép đọc dữ liệu.

## 7. Dùng selection set để kiểm tra field con được yêu cầu

`getSelectionSet()` trả về `DataFetchingFieldSelectionSet`, cho phép resolver xem client đã chọn những field con nào.

Ví dụ:

~~~graphql
query {
  book(id: "b-01") {
    id
    title
    author {
      name
    }
  }
}
~~~

Resolver:

~~~java
@QueryMapping
public Book book(DataFetchingEnvironment environment) {
    String id = environment.getArgument("id");

    DataFetchingFieldSelectionSet selectionSet =
            environment.getSelectionSet();

    boolean authorRequested =
            selectionSet.contains("author");

    return bookService.findForGraphQl(id, authorRequested);
}
~~~

Selection set có thể hỗ trợ tối ưu projection hoặc quyết định có tải một quan hệ tốn kém hay không. Tuy nhiên, đây chỉ là tín hiệu về hình dạng response mà client yêu cầu.

Khi dùng selection set, cần lưu ý:

- Query có thể chứa fragment và inline fragment.
- Alias có thể thay đổi response key.
- Field có thể được yêu cầu ở nhiều nhánh.
- Một field có thể có sub-selection lồng nhau.
- Các directive như `@skip` và `@include` ảnh hưởng field được thực thi.

Selection set không nên được dùng như một parser tự viết thay cho GraphQL engine. Hãy dùng các API selection set có sẵn và kiểm thử với fragment, alias và directive.

Cũng không nên bỏ qua kiểm tra quyền chỉ vì client không yêu cầu field trong một query hiện tại. Authorization phải được áp dụng mỗi lần field nhạy cảm được thực thi.

## 8. Truy cập DataLoader từ environment

Trong annotated controller, Spring có thể inject DataLoader trực tiếp vào tham số method. Khi viết DataFetcher thủ công, có thể lấy loader từ environment.

Ví dụ, giả sử DataLoader được đăng ký với tên `authorLoader`:

~~~java
DataFetcher<CompletableFuture<Author>> authorFetcher = environment -> {
    Book book = environment.getSource();
    DataLoader<Long, Author> loader =
            environment.getDataLoader("authorLoader");

    return loader.load(book.getAuthorId());
};
~~~

`getDataLoader(name)` lấy DataLoader đã đăng ký trong request hiện tại. `load(key)` đưa key vào hàng đợi để DataLoader gom nhiều yêu cầu và gọi batch loader.

Không tự tạo một DataLoader singleton rồi dùng chung giữa nhiều request. Spring for GraphQL tích hợp `BatchLoaderRegistry` để đăng ký DataLoader theo từng GraphQL request, giúp cache và batch có phạm vi phù hợp.

Nếu đang dùng annotated controller, cách sau thường đơn giản hơn:

~~~java
@SchemaMapping
public CompletableFuture<Author> author(
        Book book,
        DataLoader<Long, Author> authorLoader) {
    return authorLoader.load(book.getAuthorId());
}
~~~

Chỉ dùng `DataFetchingEnvironment` để lấy DataLoader khi cần làm việc trực tiếp với DataFetcher hoặc khi method đã cần environment vì các metadata khác.

## 9. DataFetchingEnvironment trong xử lý GraphQL error

Một điểm rất hữu ích của `DataFetchingEnvironment` là nó cung cấp vị trí thực thi field để tạo GraphQL error chính xác.

GraphQL response có thể chứa cả `data` và `errors`. Khi một field phát sinh lỗi, error thường cần:

- Message phù hợp cho client.
- Error classification hoặc mã lỗi.
- Path chỉ ra field gây lỗi.
- Source location trong GraphQL document nếu có.
- Extensions chứa metadata công khai cần thiết.

GraphQL Java cung cấp `GraphqlErrorBuilder.newError(environment)` để tạo error gắn với environment của field hiện tại.

Ví dụ:

~~~java
DataFetcher<Book> bookFetcher = environment -> {
    String id = environment.getArgument("id");
    Book book = bookService.findById(id);

    if (book == null) {
        throw new BookNotFoundException(id);
    }

    return book;
};
~~~

Có thể dùng Spring for GraphQL `DataFetcherExceptionResolver` để chuyển exception thành GraphQL error:

~~~java
@Component
public class BookExceptionResolver
        extends DataFetcherExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(
            Throwable exception,
            DataFetchingEnvironment environment) {

        if (exception instanceof BookNotFoundException) {
            return GraphqlErrorBuilder.newError(environment)
                    .message("Book was not found")
                    .errorType(ErrorType.NOT_FOUND)
                    .extensions(Map.of(
                            "code", "BOOK_NOT_FOUND"))
                    .build();
        }

        return null;
    }
}
~~~

`GraphqlErrorBuilder.newError(environment)` sử dụng metadata của field hiện tại để gắn path và source location thích hợp. Vì vậy, client có thể biết lỗi xảy ra ở nhánh nào của response.

Ví dụ response minh họa:

~~~json
{
  "data": {
    "book": null
  },
  "errors": [
    {
      "message": "Book was not found",
      "path": ["book"],
      "extensions": {
        "classification": "NOT_FOUND",
        "code": "BOOK_NOT_FOUND"
      }
    }
  ]
}
~~~

Cấu trúc extensions cụ thể phụ thuộc vào error classification và cấu hình của ứng dụng. Chỉ đưa metadata mà client cần xử lý; không gửi SQL, stack trace, token hoặc thông tin nội bộ.

## 10. Phân biệt lỗi request và lỗi khi resolve field

Không phải lỗi GraphQL nào cũng có `DataFetchingEnvironment`.

| Nhóm lỗi | Thời điểm | DataFetcher đã chạy? | Ví dụ |
|---|---|---:|---|
| Parse error | Phân tích document | Không | Thiếu dấu ngoặc hoặc cú pháp sai |
| Validation error | Kiểm tra query theo schema | Không | Field không tồn tại, argument sai kiểu |
| Variable coercion error | Chuyển đổi variables | Không | Truyền chuỗi vào biến Int |
| Data fetching error | Thực thi field | Có | Repository lỗi, không đủ quyền |
| Serialization error | Chuyển giá trị field thành response | Field đã được resolve | Giá trị không serialize được theo scalar |

`DataFetcherExceptionResolver` xử lý exception phát sinh trong quá trình data fetching. Nó không thay thế cơ chế xử lý parse error hoặc validation error vì các lỗi đó xảy ra trước khi DataFetcher được gọi.

Điều này giúp chọn đúng tầng xử lý:

- Lỗi cú pháp và schema contract được GraphQL engine báo trước execution.
- Lỗi coercion được xử lý bởi scalar và GraphQL validation.
- Lỗi nghiệp vụ hoặc truy cập dữ liệu được xử lý trong resolver, service và exception resolver.
- Lỗi serialize cần kiểm tra kiểu dữ liệu trả về và custom scalar.

## 11. DataFetcherResult: trả dữ liệu một phần cùng error

Có trường hợp resolver vẫn có dữ liệu chính nhưng một phần thông tin phụ không thể tải. Nếu schema và nghiệp vụ cho phép, có thể trả `DataFetcherResult` để cung cấp data cùng errors và local context.

Ví dụ:

~~~java
DataFetcher<DataFetcherResult<Book>> bookFetcher = environment -> {
    String id = environment.getArgument("id");
    Book book = bookService.findById(id);

    if (book == null) {
        GraphQLError error = GraphqlErrorBuilder.newError(environment)
                .message("Book was not found")
                .errorType(ErrorType.NOT_FOUND)
                .build();

        return DataFetcherResult.<Book>newResult()
                .data(null)
                .error(error)
                .build();
    }

    return DataFetcherResult.<Book>newResult()
            .data(book)
            .build();
};
~~~

`DataFetcherResult` có thể mang:

- `data`: giá trị của field.
- `errors`: một hoặc nhiều GraphQL errors.
- `localContext`: context được truyền tới field con.

Cách này phù hợp khi resolver cần kiểm soát rõ kết quả một phần. Nếu chỉ cần chuyển exception thành GraphQL error, `DataFetcherExceptionResolver` thường dễ quản lý hơn.

Không nên dùng partial data để che giấu lỗi làm sai tính toàn vẹn nghiệp vụ. Hãy xác định field nào có thể thiếu độc lập và field nào phải thất bại cùng nhau.

## 12. Dùng DataFetchingEnvironment với reactive DataFetcher

Spring for GraphQL hỗ trợ DataFetcher trả về `Mono` và `Flux`. Khi dùng reactive pipeline, có thể đọc các giá trị cần thiết từ environment trước khi tạo publisher.

Ví dụ:

~~~java
DataFetcher<Mono<Book>> bookFetcher = environment -> {
    String id = environment.getArgument("id");
    GraphQLContext context = environment.getGraphQlContext();
    String tenantId = context.get("tenantId");

    return bookService.findByIdAndTenant(id, tenantId);
};
~~~

Nên trích xuất các giá trị cần thiết trước khi đi vào pipeline và truyền kiểu dữ liệu cụ thể cho service. Tránh giữ toàn bộ `DataFetchingEnvironment` trong field mutable hoặc lưu nó để dùng sau khi operation kết thúc.

Ví dụ với annotated controller:

~~~java
@QueryMapping
public Mono<Book> book(DataFetchingEnvironment environment) {
    String id = environment.getArgument("id");
    String tenantId = environment.getGraphQlContext()
            .get("tenantId");

    return bookService.findByIdAndTenant(id, tenantId);
}
~~~

Không gọi `block()` hoặc `subscribe()` trong resolver. Hãy trả publisher để Spring for GraphQL quản lý quá trình thực thi và chuyển kết quả thành GraphQL response.

## 13. Những lỗi thường gặp khi sử dụng DataFetchingEnvironment

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `getArgument` trả null | Sai tên argument hoặc argument bị bỏ qua | Đối chiếu SDL và kiểm tra presence |
| Source object sai kiểu | Field cha trả về DTO khác dự kiến | Kiểm tra return type của parent resolver |
| Context không có key | Interceptor chưa đưa metadata vào GraphQLContext | Kiểm tra bước khởi tạo context |
| Dùng nhầm local context | Nhầm context toàn request với context theo nhánh | Chọn đúng `getGraphQlContext` hoặc `getLocalContext` |
| Error không có path phù hợp | Tự tạo GraphQLError mà không gắn environment | Dùng `GraphqlErrorBuilder.newError(environment)` |
| Selection set thiếu field | Không tính đến fragment, alias hoặc directive | Dùng API selection set và kiểm thử query phức tạp |
| Dữ liệu người dùng bị lẫn | Lưu environment hoặc context vào state mutable dùng chung | Giữ dữ liệu trong phạm vi request và reactive chain |
| Resolver quá phụ thuộc GraphQL Java | Truyền environment xuống service/domain | Trích xuất argument/context thành input cụ thể |

## 14. Nguyên tắc sử dụng DataFetchingEnvironment

`DataFetchingEnvironment` là công cụ mạnh, nhưng không phải method nào cũng cần nhận nó.

Nên dùng khi:

- Cần đọc nhiều argument hoặc kiểm tra argument presence.
- Cần source object trong DataFetcher thủ công.
- Cần GraphQLContext hoặc local context.
- Cần selection set để tối ưu truy vấn.
- Cần field path, alias hoặc execution metadata.
- Cần tạo GraphQL error gắn với field cụ thể.
- Cần lấy DataLoader từ environment.

Nên ưu tiên abstraction của Spring khi:

- Chỉ cần một argument: dùng `@Argument`.
- Cần source object trong controller: nhận tham số Java có kiểu cụ thể.
- Chỉ cần một context value: dùng `@ContextValue`.
- Cần tải quan hệ theo lô: dùng `@BatchMapping` hoặc DataLoader.
- Cần xử lý exception: dùng `DataFetcherExceptionResolver`.

Không nên truyền `DataFetchingEnvironment` xuyên suốt service và domain layer. Hãy trích xuất dữ liệu cần thiết tại ranh giới GraphQL, chuyển thành tham số hoặc command có kiểu rõ ràng rồi gọi service.

## 15. Kiểm thử DataFetchingEnvironment và error mapping

Có thể dùng `GraphQlTester` để kiểm tra resolver và error response trên schema thực tế.

Ví dụ kiểm tra field không tìm thấy:

~~~java
@Test
void shouldReturnNotFoundErrorForMissingBook() {
    graphQlTester.document("""
            query {
                book(id: "missing") {
                    id
                    title
                }
            }
            """)
            .execute()
            .errors()
            .satisfy(errors -> {
                assertThat(errors).isNotEmpty();
                assertThat(errors.get(0).getMessage())
                        .isEqualTo("Book was not found");
                assertThat(errors.get(0).getPath())
                        .containsExactly("book");
            });
}
~~~

Các tình huống nên kiểm thử:

1. Argument được đọc đúng từ environment.
2. Source object được truyền đúng cho field con.
3. GraphQLContext và local context có phạm vi đúng.
4. Alias được phản ánh đúng trong execution path.
5. Selection set nhận diện field được chọn qua fragment.
6. DataLoader được lấy đúng và batch function hoạt động.
7. Exception resolver tạo error có message, classification và path phù hợp.
8. Parse/validation error không bị nhầm với data fetching error.
9. DataFetcherResult trả partial data và errors đúng hợp đồng.
10. Reactive resolver không block và xử lý publisher rỗng/lỗi đúng nullability.

Nên kiểm tra cả nội dung response lẫn error path/extensions. Chỉ kiểm tra message không đủ để bảo đảm client có thể xác định đúng field gây lỗi.

## Kết luận

`DataFetchingEnvironment` là context theo từng field trong quá trình GraphQL execution. Nó cung cấp argument, source object, GraphQLContext, local context, selection set, field definition và execution path. Trong Spring for GraphQL, annotated controller có thể nhận trực tiếp environment khi cần những thông tin này.

Đặc biệt trong xử lý lỗi, environment giúp `GraphqlErrorBuilder.newError(environment)` gắn error với đúng field và path. Kết hợp với `DataFetcherExceptionResolver` hoặc `DataFetcherResult`, server có thể trả lỗi rõ ràng và dữ liệu một phần khi phù hợp. Hãy dùng environment ở ranh giới GraphQL, trích xuất dữ liệu cần thiết rồi chuyển cho service để giữ tầng nghiệp vụ độc lập và dễ kiểm thử.

## Tài liệu tham khảo

- [Spring for GraphQL — Request Execution and Error Handling](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Exception Resolution](https://docs.spring.io/spring-graphql/reference/request-execution.html#execution.exceptions)
- [GraphQL Java — DataFetchingEnvironment API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/schema/DataFetchingEnvironment.html)
- [GraphQL Java — DataFetcherResult API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/execution/DataFetcherResult.html)
