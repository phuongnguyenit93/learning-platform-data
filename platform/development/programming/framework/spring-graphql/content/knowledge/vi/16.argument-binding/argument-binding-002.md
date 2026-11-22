# @Arguments

Trong annotated controller của Spring for GraphQL, `@Arguments` dùng để bind **toàn bộ arguments của field GraphQL hiện tại** vào một tham số phương thức. Tham số đó có thể là một DTO/record gom các argument hoặc một `Map<String, Object>` khi cần xử lý linh hoạt.

Ví dụ, một field tìm kiếm có thể nhận `keyword`, `categoryId`, `minRating`, `page` và `size`. Thay vì khai báo năm tham số Java riêng biệt, controller có thể nhận một object `SearchBooksArguments` bằng `@Arguments`. Spring for GraphQL đọc các argument đã được GraphQL phân giải, chuyển chúng thành kiểu Java phù hợp rồi gọi phương thức controller.

`@Arguments` đặc biệt hữu ích khi một field có nhiều argument liên quan đến cùng một use case. Nó không lấy tất cả variables của operation hay toàn bộ nội dung query; nó chỉ bind các argument thuộc field mà resolver đang xử lý.

## 1. Phân biệt @Arguments và @Argument

Hai annotation có tên gần giống nhau nhưng mục đích khác nhau:

| Annotation | Phạm vi bind | Ví dụ |
| --- | --- | --- |
| `@Argument("filter")` | Một argument có tên cụ thể của field | Bind argument `filter` vào `BookFilter` |
| `@Arguments` | Toàn bộ arguments của field hiện tại | Bind `keyword`, `page`, `size` vào `SearchBooksArguments` |

Giả sử schema:

```graphql
type Query {
    searchBooks(
        keyword: String!
        categoryId: ID
        minRating: Int
        page: Int = 0
        size: Int = 20
    ): [Book!]!
}
```

Nếu muốn nhận riêng `keyword` và `page`, dùng `@Argument`:

```java
@QueryMapping
public List<Book> searchBooks(
        @Argument("keyword") String keyword,
        @Argument("page") Integer page) {
    return bookService.search(keyword, page);
}
```

Nếu muốn gom toàn bộ arguments thành một object, dùng `@Arguments`:

```java
public record SearchBooksArguments(
        String keyword,
        String categoryId,
        Integer minRating,
        Integer page,
        Integer size) {
}

@QueryMapping
public List<Book> searchBooks(@Arguments SearchBooksArguments arguments) {
    return bookService.search(arguments);
}
```

Với `@Arguments`, các property của object tương ứng với tên argument trong SDL. `keyword` map vào `keyword`, `categoryId` map vào `categoryId`, và tương tự với những trường còn lại.

## 2. Bind toàn bộ arguments vào DTO hoặc record

Đây là cách dùng thường gặp khi một field có nhiều tham số cùng mô tả một điều kiện tìm kiếm, phân trang hoặc command nghiệp vụ.

Schema:

```graphql
type Query {
    searchBooks(
        keyword: String!
        categoryId: ID
        minRating: Int
        page: Int = 0
        size: Int = 20
    ): [Book!]!
}
```

Java record:

```java
public record SearchBooksArguments(
        String keyword,
        String categoryId,
        Integer minRating,
        Integer page,
        Integer size) {
}
```

Controller:

```java
@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> searchBooks(@Arguments SearchBooksArguments arguments) {
        return bookService.search(arguments);
    }
}
```

Client có thể truyền một phần arguments:

```graphql
query {
    searchBooks(keyword: "Spring", minRating: 4) {
        id
        title
    }
}
```

Các giá trị mặc định trong SDL được áp dụng theo quy tắc GraphQL. Trong ví dụ, nếu client không truyền `page` và `size`, các giá trị mặc định `0` và `20` được sử dụng. Các argument nullable không có default có thể không có giá trị; vì vậy DTO thường nên dùng kiểu Java nullable như `Integer` thay vì primitive `int` nếu cần phân biệt giá trị chưa có với `0`.

Record phù hợp vì các component có tên rõ ràng, constructor ngắn và dữ liệu bất biến. Với class Java thông thường, Spring có thể bind qua constructor hoặc property binding. Nếu dùng constructor binding, cần bảo đảm tên tham số constructor có thể được phát hiện lúc chạy; cấu hình biên dịch giữ metadata tên tham số (`-parameters`) khi cần. Với property binding, class cần constructor phù hợp cùng setter hoặc property có thể ghi.

## 3. Bind vào Map<String, Object>

Khi cấu trúc arguments thay đổi linh hoạt hoặc cần xử lý theo tên ở runtime, có thể nhận toàn bộ arguments dưới dạng Map:

```java
@QueryMapping
public List<Book> searchBooks(@Arguments Map<String, Object> arguments) {
    String keyword = (String) arguments.get("keyword");
    String categoryId = (String) arguments.get("categoryId");
    Integer minRating = (Integer) arguments.get("minRating");
    Integer page = (Integer) arguments.get("page");
    Integer size = (Integer) arguments.get("size");

    return bookService.search(keyword, categoryId, minRating, page, size);
}
```

Map cho phép kiểm tra key, xử lý tập argument động hoặc chuyển tiếp dữ liệu đến một thành phần khác. Đổi lại, code mất một phần an toàn kiểu: cast sai có thể gây `ClassCastException`, và lỗi tên key chỉ được phát hiện khi chạy.

Các giá trị trong Map là kết quả coercion của GraphQL và quá trình bind. Scalar có thể xuất hiện dưới dạng `String`, `Integer`, `Boolean`, `ID` hoặc kiểu Java do scalar/coercing cấu hình. Input object thường có cấu trúc Map lồng nhau và list trở thành collection tương ứng. Nếu dùng Map, hãy kiểm tra kiểu và giá trị trước khi gọi service; tránh cast trực tiếp khi dữ liệu đến từ client.

Với phần lớn use case ổn định, DTO/record thường dễ đọc, dễ kiểm thử và có thể áp dụng Bean Validation. Dùng Map khi thật sự cần cấu trúc động hoặc muốn thao tác ở mức thấp.

## 4. Bind arguments có input object lồng nhau

`@Arguments` nhận tất cả arguments cấp field. Nếu một argument là input object, object đó được bind thành property lồng nhau trong DTO.

Schema:

```graphql
input BookFilter {
    categoryIds: [ID!]
    minRating: Int
    publishedAfter: String
}

type Query {
    searchBooks(filter: BookFilter, page: Int = 0, size: Int = 20): [Book!]!
}
```

Java DTO:

```java
public record BookFilterArguments(
        List<String> categoryIds,
        Integer minRating,
        String publishedAfter) {
}

public record SearchBooksArguments(
        BookFilterArguments filter,
        Integer page,
        Integer size) {
}
```

Controller:

```java
@QueryMapping
public List<Book> searchBooks(@Arguments SearchBooksArguments arguments) {
    return bookService.search(
        arguments.filter(),
        arguments.page(),
        arguments.size());
}
```

Client:

```graphql
query {
    searchBooks(
        filter: {
            categoryIds: ["backend", "java"]
            minRating: 4
        }
        page: 0
        size: 10
    ) {
        id
        title
    }
}
```

Trong ví dụ này, object `filter` được bind thành property `filter` của `SearchBooksArguments`; các field bên trong nó tiếp tục được bind vào `BookFilterArguments`. Cách tổ chức này giữ arguments cấp field và input object riêng biệt, đồng thời tạo DTO dễ đọc.

Nếu schema chỉ có một argument `filter: BookFilter!` và muốn nhận trực tiếp input object đó, cách rõ ràng hơn thường là `@Argument("filter") BookFilterArguments filter`. Khi dùng `@Arguments`, DTO đích phải mô tả toàn bộ arguments của field, nghĩa là có property `filter` chứa input object.

## 5. Cách binding và chuyển đổi dữ liệu

Spring for GraphQL sử dụng `GraphQlArgumentBinder` để bind argument values từ `DataFetchingEnvironment` vào kiểu Java của tham số controller. Binder hỗ trợ constructor binding và property binding, bao gồm object lồng nhau, collection, array và Map.

Quy trình khái quát:

1. GraphQL parse operation và kiểm tra arguments với schema.
2. GraphQL áp dụng variable coercion và default value theo SDL.
3. Spring lấy toàn bộ arguments của field hiện tại.
4. `GraphQlArgumentBinder` chuyển các giá trị sang kiểu Java đích và bind vào DTO/record hoặc Map.
5. Nếu binding thành công, Spring gọi phương thức controller với object đã bind.

Sơ đồ:

```mermaid
flowchart TD
    A[GraphQL operation] --> B[Validate schema và coerce arguments]
    B --> C[DataFetchingEnvironment]
    C --> D[@Arguments resolver]
    D --> E[GraphQlArgumentBinder]
    E --> F[Constructor/property binding]
    F --> G[DTO, record hoặc Map]
    G --> H[Annotated controller method]
    H --> I[Application service]
```

Binding không thay thế validation nghiệp vụ. Ví dụ `size` có thể bind thành `Integer`, nhưng việc `size` phải nằm trong khoảng 1 đến 100 là quy tắc ứng dụng. Nên kiểm tra các giới hạn đó trước khi truy vấn database.

## 6. Argument name và Java property name

Với DTO hoặc record, tên component/property cần khớp với tên argument trong GraphQL. GraphQL phân biệt chữ hoa chữ thường, do đó `categoryId` và `categoryID` là hai tên khác nhau.

Ví dụ SDL:

```graphql
type Query {
    booksByAuthor(authorId: ID!, includeDrafts: Boolean = false): [Book!]!
}
```

DTO tương ứng:

```java
public record BooksByAuthorArguments(
        String authorId,
        Boolean includeDrafts) {
}
```

```java
@QueryMapping
public List<Book> booksByAuthor(@Arguments BooksByAuthorArguments arguments) {
    return bookService.findByAuthor(
        arguments.authorId(),
        Boolean.TRUE.equals(arguments.includeDrafts()));
}
```

Không dùng tên property tùy ý như `author` để nhận argument `authorId` nếu không có cơ chế mapping tương ứng. Nếu cần một tên Java khác với tên GraphQL, hãy cân nhắc nhận Map rồi chuyển đổi tường minh, hoặc thiết kế DTO/property phù hợp với contract schema.

## 7. Phân biệt argument bị bỏ qua và argument có giá trị null

GraphQL phân biệt argument không được truyền với argument được truyền tường minh là `null`. Điều này quan trọng với mutation cập nhật một phần. Ví dụ:

```graphql
type Mutation {
    updateBook(id: ID!, subtitle: String): Book!
}
```

Client có thể gửi:

```graphql
mutation {
    updateBook(id: "book-01") {
        id
        subtitle
    }
}
```

Ở đây `subtitle` bị bỏ qua; ứng dụng có thể giữ nguyên subtitle hiện tại. Nếu client gửi `subtitle: null`, ứng dụng có thể hiểu là xóa subtitle. Một DTO dùng `String subtitle` thông thường có thể nhận `null` trong cả hai tình huống, làm mất thông tin về việc argument có được cung cấp hay không.

Spring for GraphQL cung cấp `ArgumentValue<T>` để biểu diễn cả giá trị lẫn trạng thái omitted:

```java
public record UpdateBookArguments(
        String id,
        ArgumentValue<String> subtitle) {
}

@MutationMapping
public Book updateBook(@Arguments UpdateBookArguments arguments) {
    if (arguments.subtitle().isOmitted()) {
        return bookService.updateWithoutChangingSubtitle(arguments.id());
    }

    return bookService.updateSubtitle(
        arguments.id(), arguments.subtitle().value());
}
```

Khi argument bị bỏ qua, `ArgumentValue` cho biết trạng thái omitted. Khi argument được truyền với một chuỗi, `value()` chứa chuỗi đó; khi truyền explicit `null`, argument được xem là đã cung cấp và giá trị là `null`. Nhờ vậy service có thể phân biệt giữ nguyên giá trị với xóa giá trị.

Nếu schema khai báo argument non-null (`String!`), client không thể truyền `null` hợp lệ. `ArgumentValue` vẫn hữu ích cho những argument nullable mà nghiệp vụ cần phân biệt omitted và explicit null.

## 8. Kết hợp @Arguments với source object và tham số khác

`@Arguments` có thể được dùng cùng source object trong một resolver field lồng nhau. Ví dụ, một field `Book.reviews` nhận thêm điều kiện lọc:

```graphql
type Book {
    reviews(minRating: Int, limit: Int = 10): [Review!]!
}
```

```java
public record ReviewArguments(Integer minRating, Integer limit) {
}

@Controller
public class BookFieldController {

    private final ReviewService reviewService;

    public BookFieldController(ReviewService reviewService) {
        this.reviewService = reviewService;
    }

    @SchemaMapping(typeName = "Book", field = "reviews")
    public List<Review> reviews(
            Book book,
            @Arguments ReviewArguments arguments) {
        return reviewService.findByBook(
            book.id(), arguments.minRating(), arguments.limit());
    }
}
```

`Book book` là source object của field `reviews`; `ReviewArguments` nhận toàn bộ arguments của chính field đó. Hai tham số phục vụ hai vai trò khác nhau và có thể cùng xuất hiện trong một method mapping.

Resolver cũng có thể nhận các tham số đặc biệt khác mà Spring hỗ trợ, chẳng hạn `DataFetchingEnvironment`, `Principal`, `GraphQLContext` hoặc context value. Những tham số đó không thuộc dữ liệu được bind bởi `@Arguments`; chúng được phân giải từ execution context của request.

## 9. Validation cho object được bind

DTO gom arguments là vị trí phù hợp để áp dụng validation. Ví dụ:

```java
public record SearchBooksArguments(
        @NotBlank String keyword,
        @Min(1) @Max(100) Integer size,
        @Min(0) Integer page) {
}
```

Controller có thể đánh dấu tham số cần validate:

```java
@QueryMapping
public List<Book> searchBooks(@Arguments @Valid SearchBooksArguments arguments) {
    return bookService.search(arguments);
}
```

Ứng dụng cần có Bean Validation implementation và cấu hình Spring validation phù hợp. Các annotation như `@NotBlank`, `@Min` và `@Max` kiểm tra quy tắc dữ liệu trước khi service thực thi. Nên kiểm tra cả giới hạn liên trường trong service hoặc custom validator, ví dụ `page * size` không được vượt giới hạn truy vấn cho phép.

Validation của GraphQL schema và Bean Validation giải quyết hai lớp khác nhau:

- GraphQL kiểm tra kiểu, required argument, enum, scalar coercion và default value theo SDL.
- Bean Validation kiểm tra ràng buộc dữ liệu ứng dụng như chuỗi không rỗng, số nằm trong khoảng hoặc tổ hợp trường hợp lệ.
- Service/domain vẫn phải bảo vệ invariant nghiệp vụ và quyền truy cập, kể cả khi cùng logic được gọi từ entry point khác.

## 10. Xử lý lỗi binding

Nếu tên argument không khớp, kiểu Java không thể nhận giá trị hoặc cấu trúc nested object không bind được, phương thức controller có thể không được gọi. `GraphQlArgumentBinder` thu thập lỗi binding và báo lỗi thay vì âm thầm tạo DTO sai dữ liệu.

Ví dụ, SDL khai báo `size: Int` nhưng client truyền một giá trị không thể coercion thành số nguyên. Lỗi có thể bị phát hiện ngay ở bước GraphQL input coercion. Nếu GraphQL chấp nhận giá trị nhưng Java DTO không thể bind sang kiểu đích, lỗi phát sinh ở bước argument binding.

Spring for GraphQL cho phép xử lý exception từ data fetcher bằng `DataFetcherExceptionResolver` hoặc `DataFetcherExceptionResolverAdapter`. Có thể ánh xạ lỗi binding thành thông điệp an toàn và mã lỗi phù hợp trong `extensions`, đồng thời ghi chi tiết kỹ thuật ở server log. Không nên trả stack trace, tên class nội bộ hoặc dữ liệu đầu vào nhạy cảm cho client.

Khi debug, kiểm tra theo thứ tự:

1. Tên argument trong SDL có khớp tên property/record component không?
2. Argument có nullable hay non-null, có default value hay không?
3. Giá trị client gửi có đúng GraphQL input type không?
4. Kiểu Java đích có thể nhận giá trị sau coercion không?
5. Với object lồng nhau, các property và constructor có bind được không?
6. Nếu binding thành công, service có từ chối dữ liệu theo business rule không?

## 11. Kiểm thử @Arguments bằng GraphQlTester

`GraphQlTester` cho phép gửi operation với nhiều arguments và variables, sau đó kiểm tra kết quả của resolver.

Ví dụ:

```java
graphQlTester.document("""
        query SearchBooks(
            $keyword: String!
            $minRating: Int
            $size: Int
        ) {
            searchBooks(
                keyword: $keyword
                minRating: $minRating
                size: $size
            ) {
                id
                title
            }
        }
        """)
    .variable("keyword", "Spring")
    .variable("minRating", 4)
    .variable("size", 10)
    .execute()
    .path("searchBooks")
    .entityList(Book.class)
    .hasSize(3);
```

Nên có các test bao phủ:

- Tất cả arguments được bind đúng vào record/DTO.
- Argument bị bỏ qua sử dụng default value trong SDL.
- Argument nullable được bind khi client gửi `null`.
- Nested input object và list được bind đúng cấu trúc.
- Tên argument sai hoặc kiểu dữ liệu không hợp lệ tạo GraphQL error phù hợp.
- `ArgumentValue` phân biệt omitted và explicit null trong mutation cập nhật.
- Bean Validation từ chối giá trị ngoài giới hạn.
- Resolver `@SchemaMapping` nhận đồng thời source object và `@Arguments` đúng dữ liệu.

Ngoài kiểm tra response, có thể mock service và verify service nhận đúng object arguments đã bind. Với các trường hợp lỗi, kiểm tra cả `errors` và việc resolver/service không bị gọi khi lỗi xảy ra trước bước invocation.

## 12. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| DTO nhận toàn `null` | Tên property không khớp tên argument hoặc constructor binding thiếu metadata | Kiểm tra tên và cấu hình parameter names; cân nhắc dùng record |
| Chỉ nhận một phần arguments | DTO thiếu property hoặc kiểu bind không tương thích | Bổ sung component/property và kiểm tra kiểu |
| Nhầm `@Arguments` với input object | `@Arguments` bind toàn bộ arguments cấp field | Dùng `@Argument("filter")` nếu chỉ muốn một input object |
| `Map` gây `ClassCastException` | Giá trị runtime không phải kiểu cast dự kiến | Kiểm tra kiểu hoặc dùng DTO có kiểu rõ ràng |
| Optional number thành `0` ngoài dự kiến | Dùng primitive cho argument có thể bị bỏ qua/null | Dùng wrapper như `Integer` hoặc `ArgumentValue<Integer>` |
| Không phân biệt omitted và null | DTO chỉ dùng nullable field thông thường | Dùng `ArgumentValue<T>` |
| Binding lỗi trước khi vào controller | SDL, coercion hoặc Java target không tương thích | Kiểm tra schema, input và binder error |
| Dùng `@Arguments` nhưng muốn lấy variables | Nhầm arguments của field với operation variables | Bind argument được tham chiếu bởi variable; không dùng `@Arguments` để đọc variables toàn cục |

## 13. Nguyên tắc sử dụng @Arguments

Dùng `@Arguments` khi một field có nhiều argument cùng tạo thành một bộ điều kiện hoặc command. Ưu tiên record/DTO có kiểu rõ ràng để tận dụng constructor binding, validation và khả năng refactor an toàn. Chọn Map khi cần xử lý cấu trúc thực sự động và chấp nhận tự kiểm tra kiểu.

Nếu chỉ có một argument, `@Argument` thường diễn đạt ý định rõ hơn. Nếu field có một input object duy nhất và muốn nhận trực tiếp object đó, bind bằng `@Argument("input")`. Dùng `@Arguments` khi cần nhận toàn bộ argument cấp field, bao gồm cả các argument riêng lẻ và input object lồng nhau.

Chú ý default value, nullability và sự khác nhau giữa omitted với explicit null. Đặt validation ở DTO cho các ràng buộc dữ liệu, còn invariant và authorization vẫn thuộc tầng service/domain. Trong Spring for GraphQL, `@Arguments` giúp controller nhận một bộ tham số có cấu trúc, giảm method signature dài và giữ logic xử lý query/mutation rõ ràng.
