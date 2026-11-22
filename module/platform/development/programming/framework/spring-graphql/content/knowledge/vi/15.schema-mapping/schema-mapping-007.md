# Method argument resolution

Trong Spring for GraphQL, một handler method có thể nhận nhiều loại tham số: argument do client gửi, object nguồn từ field cha, dữ liệu trong GraphQL context hoặc execution environment. **Method argument resolution** là cơ chế Spring phân giải những giá trị đó và truyền chúng vào đúng tham số Java khi DataFetcher gọi handler.

Hiểu rõ cơ chế này giúp tránh nhầm lẫn giữa argument của field hiện tại và source object, bind input object an toàn vào record/DTO, phân biệt field bị bỏ qua với field được truyền null, đồng thời chia sẻ dữ liệu request qua context. Đây là nền tảng để viết resolver bằng **@QueryMapping**, **@MutationMapping** và **@SchemaMapping** mà không phải thao tác trực tiếp với DataFetchingEnvironment trong mọi method.

Bài này trình bày cách Spring chọn và bind tham số handler, cách dùng **@Argument** và **@Arguments**, cách nhận source object, GraphQL context, Principal và DataFetchingEnvironment, cùng validation, xử lý lỗi binding và kiểm thử.

## 1. Method argument resolution là gì?

GraphQL Java gọi một DataFetcher khi cần resolve field. Với annotated controller, Spring đăng ký DataFetcher làm adapter để gọi method Java. Trước khi gọi method, Spring phải xác định giá trị cho từng tham số.

Ví dụ schema:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
}
~~~

Handler:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String bookId) {
        return bookService.findById(bookId);
    }
}
~~~

Khi client gửi query với ID, Spring:

1. Nhận DataFetchingEnvironment của field Query.book.
2. Đọc argument có tên id.
3. Chuyển giá trị sang kiểu Java String được khai báo.
4. Gọi method book với tham số bookId.
5. Chuyển giá trị method trả về thành kết quả DataFetcher.

Việc tìm đúng giá trị cho mỗi tham số được thực hiện bởi hệ thống method argument resolvers. Mỗi loại tham số được nhận diện theo annotation hoặc kiểu dữ liệu, sau đó được lấy từ GraphQL execution context.

## 2. Các nguồn dữ liệu có thể truyền vào handler

Một method handler có thể nhận dữ liệu từ nhiều nguồn khác nhau:

| Nguồn | Cách nhận | Dùng khi |
|---|---|---|
| Argument của field | **@Argument** | Lấy một giá trị hoặc input object client gửi |
| Toàn bộ arguments | **@Arguments** | Cần bind nhiều arguments thành Map/DTO |
| Source object | Tham số kiểu Java tương ứng | Resolve field con của object cha |
| GraphQL context | **@ContextValue** hoặc GraphQLContext | Dữ liệu dùng chung trong một request |
| Local context | **@LocalContextValue** | Dữ liệu được truyền theo một nhánh field |
| Execution environment | **DataFetchingEnvironment** | Cần truy cập thông tin GraphQL ở mức thấp |
| Người dùng hiện tại | **Principal** | Lấy principal đã xác thực nếu được tích hợp |

Không phải mọi method đều cần tất cả các nguồn. Nên khai báo đúng những tham số handler thực sự sử dụng để chữ ký method dễ đọc và dễ kiểm thử.

## 3. Lấy một argument bằng @Argument

**@Argument** dùng để lấy một argument cụ thể của GraphQL field và bind nó vào tham số Java.

SDL:

~~~graphql
type Query {
  book(id: ID!, includeArchived: Boolean = false): Book
}
~~~

Handler:

~~~java
@QueryMapping
public Book book(
        @Argument("id") String bookId,
        @Argument("includeArchived") Boolean includeArchived) {

    return bookService.findById(bookId, includeArchived);
}
~~~

Tên trong **@Argument** là tên argument trong SDL. Tên biến Java có thể khác tên GraphQL:

- GraphQL argument: **id**
- Java parameter: **bookId**

Nếu không truyền tên trong annotation, Spring có thể suy ra tên argument từ tên tham số Java. Cách suy luận này phụ thuộc metadata tên tham số có sẵn trong bytecode. Để tránh lỗi do cấu hình compiler hoặc refactor tên biến, có thể khai báo tên tường minh.

~~~java
@QueryMapping
public Book book(@Argument("id") String id) {
    return bookService.findById(id);
}
~~~

### Kiểu Java cần tương thích với GraphQL type

Các scalar GraphQL thường được bind vào kiểu Java tương ứng:

| GraphQL type | Kiểu Java thường dùng |
|---|---|
| **ID** | String |
| **String** | String |
| **Int** | Integer |
| **Float** | Double |
| **Boolean** | Boolean |
| **Enum** | Java enum tương ứng |
| **[T]** | List/Collection/array của kiểu T |
| **Input object** | Java record hoặc DTO |

Với custom scalar, kiểu Java phụ thuộc scalar implementation và cấu hình coercing. Không nên giả định mọi custom scalar đều tự động bind thành String.

GraphQL thực hiện parse và input coercion trước khi gọi resolver. Vì vậy, handler thường nhận giá trị đã được GraphQL chuyển đổi theo kiểu schema, sau đó Spring tiếp tục bind vào kiểu Java đích.

## 4. Bind input object vào record hoặc DTO

Khi mutation nhận nhiều giá trị có cấu trúc, nên gom chúng vào input object.

SDL:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
  status: BookStatus = DRAFT
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
~~~

Java record:

~~~java
public record CreateBookInput(
        String title,
        String authorId,
        BookStatus status) {
}
~~~

Handler:

~~~java
@MutationMapping
public Book createBook(@Argument("input") CreateBookInput input) {
    return bookService.create(input);
}
~~~

Spring for GraphQL sử dụng **GraphQlArgumentBinder** để bind giá trị argument vào kiểu Java đích. Binder hỗ trợ constructor binding và property binding, bao gồm cấu trúc object lồng nhau, collection và map.

### Constructor binding

Với Java record, các component của record được dùng để tạo instance:

~~~java
public record AddressInput(
        String street,
        String city,
        String postalCode) {
}

public record CreateBookInput(
        String title,
        String authorId,
        AddressInput shippingAddress) {
}
~~~

Khi variables có cấu trúc lồng nhau, Spring bind object con thành AddressInput rồi truyền vào constructor của CreateBookInput.

### Property binding

Với JavaBean có constructor mặc định và setter, binder có thể gán giá trị vào property:

~~~java
public class BookFilter {

    private String titlePrefix;
    private BookStatus status;

    public String getTitlePrefix() {
        return titlePrefix;
    }

    public void setTitlePrefix(String titlePrefix) {
        this.titlePrefix = titlePrefix;
    }

    public BookStatus getStatus() {
        return status;
    }

    public void setStatus(BookStatus status) {
        this.status = status;
    }
}
~~~

Record thường phù hợp với input DTO bất biến và có cấu trúc rõ. JavaBean có thể hữu ích khi cần property binding hoặc tương thích với mô hình dữ liệu hiện có. Dù dùng kiểu nào, chỉ nên nhận các field được khai báo trong GraphQL input type và cần cho use case.

## 5. GraphQlArgumentBinder chuyển đổi dữ liệu như thế nào?

GraphQL input object sau coercion thường được biểu diễn dưới dạng Map và collection. GraphQlArgumentBinder chuyển cấu trúc đó thành object Java:

~~~text
GraphQL variables
      |
      v
GraphQL input coercion
      |
      v
Map / List / scalar values
      |
      v
GraphQlArgumentBinder
      |
      +--> Constructor binding
      |
      +--> Property binding
      |
      v
Java record / DTO / collection
      |
      v
Annotated handler method
~~~

Binder sử dụng conversion service và cơ chế binding của Spring để xử lý kiểu dữ liệu. Nếu cấu trúc hoặc giá trị không thể bind vào kiểu Java đích, quá trình binding có thể phát sinh lỗi thay vì âm thầm tạo một object sai.

Ví dụ, SDL khai báo:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
}
~~~

Nhưng Java record lại khai báo:

~~~java
public record CreateBookInput(
        String title,
        Long authorId) {
}
~~~

Giá trị ID có thể được coercion thành dạng chuỗi; việc bind sang Long phụ thuộc conversion có sẵn và định dạng ID. Nếu ID của domain là chuỗi opaque, nên dùng String thay vì ép sang số chỉ vì một vài ID mẫu có dạng số.

### Đặt tên field nhất quán

Tên field trong input object nên tương ứng với property hoặc constructor parameter Java. Nếu SDL dùng camelCase, Java record cũng nên dùng camelCase:

~~~graphql
input BookFilterInput {
  titlePrefix: String
  minimumPageCount: Int
}
~~~

~~~java
public record BookFilterInput(
        String titlePrefix,
        Integer minimumPageCount) {
}
~~~

Tên không khớp hoặc kiểu không tương thích là nguyên nhân thường gặp khiến argument binding thất bại.

## 6. Bind toàn bộ arguments bằng @Arguments

Nếu một field có nhiều argument và handler cần nhận cả nhóm, có thể dùng **@Arguments**. Spring bind toàn bộ arguments thành Map hoặc JavaBean/DTO.

SDL:

~~~graphql
type Query {
  searchBooks(
    titlePrefix: String
    status: BookStatus
    first: Int = 20
  ): [Book!]!
}
~~~

Nhận dưới dạng Map:

~~~java
@QueryMapping
public List<Book> searchBooks(@Arguments Map<String, Object> arguments) {
    String titlePrefix = (String) arguments.get("titlePrefix");
    BookStatus status = (BookStatus) arguments.get("status");
    Integer first = (Integer) arguments.get("first");

    return bookService.search(titlePrefix, status, first);
}
~~~

Nhận bằng DTO:

~~~java
public record BookSearchArguments(
        String titlePrefix,
        BookStatus status,
        Integer first) {
}
~~~

~~~java
@QueryMapping
public List<Book> searchBooks(@Arguments BookSearchArguments arguments) {
    return bookService.search(
            arguments.titlePrefix(),
            arguments.status(),
            arguments.first());
}
~~~

**@Arguments** hữu ích khi nhiều argument tạo thành một nhóm điều kiện tìm kiếm. Nếu method chỉ cần một hoặc hai giá trị, **@Argument** thường làm ý định rõ ràng hơn.

Map linh hoạt nhưng phải ép kiểu và kiểm tra null thủ công. DTO có kiểu tĩnh, dễ refactor và thuận tiện áp dụng validation hơn.

## 7. Phân biệt argument với source object

Đây là điểm rất quan trọng khi viết **@SchemaMapping**.

Argument là dữ liệu client truyền cho field hiện tại. Source object là kết quả đã được resolve từ field cha và được dùng làm đầu vào để resolve field con.

SDL:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  author(language: String): Author
}

type Author {
  id: ID!
  name: String!
}
~~~

Controller:

~~~java
@Controller
public class BookController {

    private final BookService bookService;
    private final AuthorService authorService;

    public BookController(
            BookService bookService,
            AuthorService authorService) {
        this.bookService = bookService;
        this.authorService = authorService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id);
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(
            Book source,
            @Argument("language") String language) {

        return authorService.findById(
                source.getAuthorId(),
                language);
    }
}
~~~

Trong method author:

- **Book source** là object cha đã được resolve bởi Query.book.
- **@Argument("language")** là argument của field Book.author do client gửi.

Query:

~~~graphql
query {
  book(id: "book-01") {
    title
    author(language: "vi") {
      name
    }
  }
}
~~~

Khi Query.book trả về một Book, GraphQL dùng Book đó làm source cho field author. Spring truyền source object vào tham số Book và lấy language từ argument của field author.

Không nhầm source object với argument có tên book. Client không cần gửi lại toàn bộ Book trong query con; object cha đã có sẵn trong execution context.

## 8. Suy luận source type trong @SchemaMapping

Với **@SchemaMapping**, Spring có thể suy ra GraphQL type chứa field từ kiểu source object của handler:

~~~java
@SchemaMapping
public Author author(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

Trong ví dụ này:

- Source type Java là Book.
- Tên method là author.
- Spring có thể suy ra mapping tương ứng với Book.author.

Nếu tên method khác field hoặc source type không đủ rõ, hãy chỉ định tường minh:

~~~java
@SchemaMapping(typeName = "Book", field = "primaryAuthor")
public Author loadAuthor(Book source) {
    return authorService.findById(source.getAuthorId());
}
~~~

Khi một method nhận nhiều tham số, cần bảo đảm source object được nhận diện rõ ràng. Các tham số đã có annotation như **@Argument** hoặc có kiểu đặc biệt như **DataFetchingEnvironment** được xử lý theo resolver tương ứng; tham số còn lại có thể được dùng làm source nếu phù hợp với mapping.

Nếu chữ ký method mơ hồ hoặc có nhiều tham số không thể phân giải, Spring báo lỗi khi phát hiện hoặc gọi handler. Không nên dùng nhiều tham số Java không annotation với kỳ vọng framework tự đoán ý nghĩa.

## 9. Giữ khác biệt giữa omitted và null bằng ArgumentValue

Với argument nullable, GraphQL phân biệt hai trường hợp:

- Client không gửi argument.
- Client gửi argument với giá trị null.

Trong một số mutation cập nhật, hai trạng thái này có ý nghĩa khác nhau. Ví dụ, bỏ qua description có thể là giữ nguyên giá trị cũ, còn gửi null có thể là xóa mô tả.

Nếu bind trực tiếp vào String hoặc DTO field nullable, cả hai trường hợp có thể cùng trở thành Java null. **ArgumentValue<T>** cho phép giữ thông tin argument có bị bỏ qua hay không.

SDL:

~~~graphql
type Query {
  books(filter: BookFilterInput): [Book!]!
}
~~~

Handler:

~~~java
@QueryMapping
public List<Book> books(
        @Argument("filter") ArgumentValue<BookFilterInput> filter) {

    if (filter.isOmitted()) {
        return bookService.findDefaultBooks();
    }

    if (filter.value() == null) {
        return bookService.findBooksWithoutFilter();
    }

    return bookService.search(filter.value());
}
~~~

Ở đây:

- Không truyền filter: ArgumentValue cho biết argument bị omitted.
- Truyền filter: null: argument có mặt nhưng giá trị là null.
- Truyền một object: value chứa BookFilterInput đã bind.

Nếu SDL khai báo argument non-null, client không thể bỏ qua hoặc truyền null hợp lệ; khi đó không cần dùng ArgumentValue để phân biệt hai trạng thái này.

ArgumentValue đặc biệt hữu ích cho patch/update semantics. Hãy kiểm thử riêng omitted, explicit null và object có giá trị để tránh vô tình xóa dữ liệu.

## 10. Nhận dữ liệu từ GraphQLContext bằng @ContextValue

GraphQLContext là vùng lưu dữ liệu dùng chung trong một lần thực thi GraphQL. Dữ liệu có thể được thêm từ WebGraphQlInterceptor hoặc thành phần xử lý request trước khi operation chạy.

Ví dụ handler lấy tenant ID:

~~~java
@QueryMapping
public List<Book> books(
        @ContextValue("tenantId") String tenantId) {

    return bookService.findForTenant(tenantId);
}
~~~

Giá trị tenantId phải được server đưa vào GraphQLContext trước đó. Handler không nên tự tin tưởng tenant ID do client gửi trong argument.

Một interceptor có thể đọc thông tin đã được xác thực và đưa vào execution input:

~~~java
@Component
public class TenantContextInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String tenantId = resolveTenantFromAuthenticatedRequest(request);

        request.configureExecutionInput((input, builder) ->
                builder.graphQLContext(context ->
                        context.put("tenantId", tenantId))
                    .build());

        return chain.next(request);
    }
}
~~~

Đây là ví dụ minh họa; cách lấy tenant phải dựa trên authentication và mô hình multi-tenant của ứng dụng. GraphQLContext có thể được đọc từ nhiều handler trong cùng execution mà không phải truyền tenant qua từng argument của client.

Nếu key không tồn tại, cách xử lý phụ thuộc cấu hình required/optional của **@ContextValue** và kiểu tham số. Với dữ liệu bắt buộc như tenant hoặc principal, nên để lỗi được phát hiện sớm và không âm thầm dùng giá trị mặc định thiếu an toàn.

## 11. Local context với @LocalContextValue

GraphQL cũng có local context để truyền dữ liệu theo một nhánh của cây field. Khác với GraphQLContext dùng chung cho execution, local context được truyền từ một DataFetcher cha xuống các field con liên quan.

Một DataFetcher có thể trả **DataFetcherResult** chứa data và local context:

~~~java
DataFetcherResult<Book> result = DataFetcherResult.<Book>newResult()
        .data(book)
        .localContext(Map.of("displayCurrency", "VND"))
        .build();
~~~

Handler của field con có thể nhận giá trị:

~~~java
@SchemaMapping(typeName = "Book", field = "price")
public Money price(
        Book book,
        @LocalContextValue("displayCurrency") String currency) {

    return pricingService.convert(book.getPrice(), currency);
}
~~~

Local context hữu ích khi thông tin chỉ có ý nghĩa trong nhánh đang resolve, chẳng hạn locale hiển thị, currency hoặc một lựa chọn xử lý đã được xác định ở field cha.

Không nên dùng local context thay cho dữ liệu domain chính. Nếu dữ liệu là một phần ổn định của Book hoặc Author, hãy biểu diễn nó trong model hoặc service phù hợp. Context nên chứa thông tin phục vụ execution.

## 12. DataFetchingEnvironment cho trường hợp cần truy cập mức thấp

Nếu các tham số annotation chưa đủ, handler có thể nhận **DataFetchingEnvironment**:

~~~java
@QueryMapping
public Book book(
        @Argument("id") String id,
        DataFetchingEnvironment environment) {

    GraphQLContext graphQLContext = environment.getGraphQlContext();
    String operationPath = environment.getExecutionStepInfo()
            .getPath()
            .toString();

    return bookService.findById(id);
}
~~~

DataFetchingEnvironment cung cấp nhiều thông tin:

- Arguments của field hiện tại.
- Source object.
- GraphQLContext và local context.
- Field definition và selection set.
- ExecutionStepInfo và đường dẫn field.
- GraphQL schema và thông tin execution.

Ví dụ lấy argument trực tiếp:

~~~java
String id = environment.getArgument("id");
~~~

Tuy nhiên, nếu method chỉ cần một argument, nên dùng **@Argument**. Annotation thể hiện rõ dữ liệu method cần và tránh để business code phụ thuộc trực tiếp vào GraphQL Java API.

DataFetchingEnvironment phù hợp với adapter hoặc resolver cần lựa chọn hành vi theo selection set, execution path hoặc metadata GraphQL cụ thể. Không nên chuyển nó sâu vào service layer.

## 13. Principal và thông tin xác thực

Khi tích hợp Spring Security, handler có thể nhận **Principal** nếu principal của request được cung cấp trong GraphQL execution context:

~~~java
@QueryMapping
public List<Book> myBooks(Principal principal) {
    return bookService.findOwnedBy(principal.getName());
}
~~~

Principal đại diện cho danh tính đã được xác thực. Nó khác với argument do client gửi:

- Argument là dữ liệu request và có thể bị client thay đổi.
- Principal được tạo từ quá trình authentication ở server.

Không nên dùng một argument như userId hoặc ownerId làm căn cứ duy nhất để xác định dữ liệu của người gọi. Nếu API cho phép truy vấn tài nguyên của người khác, service cần kiểm tra authorization cho resource đó.

Nếu request không có principal, handler phải xử lý trường hợp chưa xác thực theo chính sách của ứng dụng. Có thể bảo vệ field bằng Spring Security hoặc method security và trả lỗi authorization nhất quán.

## 14. Validation và lỗi trong quá trình argument binding

Có nhiều lớp kiểm tra trước khi handler hoàn thành:

1. GraphQL parse và validate operation.
2. GraphQL kiểm tra argument có tồn tại và đúng kiểu schema.
3. GraphQL coercion variables và input literals.
4. Spring bind giá trị argument vào kiểu Java.
5. Bean Validation kiểm tra constraint nếu được kích hoạt.
6. Service kiểm tra quy tắc nghiệp vụ và quyền.

Ví dụ input:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
~~~

Java record:

~~~java
public record CreateBookInput(
        @NotBlank String title,
        @NotBlank String authorId) {
}
~~~

Handler:

~~~java
@MutationMapping
public Book createBook(
        @Argument("input") @Valid CreateBookInput input) {
    return bookService.create(input);
}
~~~

Ứng dụng cần có Jakarta Bean Validation provider, thường thông qua **spring-boot-starter-validation**. Với Spring Boot 3, annotation thuộc namespace **jakarta.validation**.

### Binding error khác business error

Binding error xảy ra khi Spring không thể chuyển giá trị GraphQL thành kiểu Java đích hoặc không thể bind cấu trúc vào DTO. Ví dụ constructor không phù hợp, kiểu Java không chuyển đổi được hoặc cấu trúc input không tương thích.

Business error xảy ra sau khi dữ liệu đã bind thành công nhưng không thỏa mãn quy tắc nghiệp vụ, ví dụ author ID không tồn tại hoặc user không có quyền cập nhật.

Không nên xử lý hai nhóm lỗi như nhau:

- Binding/validation error thường phản ánh request không phù hợp với input contract.
- Business error phản ánh trạng thái domain hoặc điều kiện của use case.

Spring for GraphQL có thể chuyển lỗi binding hoặc validation thành GraphQL error qua cơ chế exception handling. Nếu API dùng payload object và muốn trả lỗi validation trong payload, cần chủ động chuyển đổi chúng theo contract; chỉ thêm @Valid không tự điền userErrors.

## 15. Tránh lạm dụng DataFetchingEnvironment và context

Method argument resolution giúp handler chỉ nhận đúng dữ liệu cần thiết. Một số dấu hiệu cho thấy handler đang phụ thuộc quá nhiều vào GraphQL execution:

- Method nhận DataFetchingEnvironment chỉ để đọc một argument đơn giản.
- Service nhận DataFetchingEnvironment hoặc GraphQLContext.
- Nhiều resolver tự đọc cùng một header hoặc tự phân tích authentication.
- Business logic phụ thuộc tên field hoặc selection set.
- Client phải gửi tenant/user ID dù server đã xác thực được danh tính.

Có thể cải thiện:

- Dùng **@Argument** cho dữ liệu input.
- Dùng source object cho field con.
- Dùng **@ContextValue** cho request metadata do server tạo.
- Dùng Principal cho danh tính đã xác thực.
- Chuyển dữ liệu thành command/query object trước khi gọi service.
- Chỉ giữ DataFetchingEnvironment ở adapter layer khi thực sự cần GraphQL metadata.

Ví dụ:

~~~java
@MutationMapping
public Book updateBook(
        @Argument("input") UpdateBookInput input,
        Principal principal) {

    UpdateBookCommand command = new UpdateBookCommand(
            input.id(),
            input.title(),
            principal.getName());

    return bookService.update(command);
}
~~~

Service nhận command có kiểu rõ ràng thay vì phụ thuộc vào GraphQL argument hoặc execution environment.

## 16. Method argument resolution trong @BatchMapping

Với field resolver thông thường, source object thường là một object:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

Với **@BatchMapping**, handler nhận một danh sách source object:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> author(List<Book> books) {
    List<String> ids = books.stream()
            .map(Book::getAuthorId)
            .distinct()
            .toList();

    Map<String, Author> authors = authorService.findAllByIds(ids);

    Map<Book, Author> result = new HashMap<>();
    for (Book book : books) {
        Author author = authors.get(book.getAuthorId());
        if (author != null) {
            result.put(book, author);
        }
    }
    return result;
}
~~~

Tham số **List<Book>** ở đây không phải list argument do client gửi. Nó là nhóm source object được framework gom để batch resolve field author.

Phân biệt hai trường hợp:

- **@Argument List<BookFilter>**: danh sách do client truyền vào field.
- **List<Book>** trong handler **@BatchMapping**: danh sách parent/source object mà framework gom lại.

Nếu field có argument riêng trong schema, cần kiểm tra cách thiết kế batch mapping và DataLoader để bảo đảm mỗi giá trị argument vẫn được áp dụng đúng cho từng source hoặc được xử lý theo key phù hợp.

## 17. Kiểm thử method argument resolution bằng GraphQlTester

GraphQlTester cho phép kiểm tra operation và kết quả handler ở mức GraphQL execution.

Ví dụ kiểm thử argument và source object:

~~~java
@SpringBootTest
class BookArgumentResolutionTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void shouldBindArgumentAndResolveNestedField() {
        graphQlTester.document("""
                query FindBook($id: ID!) {
                    book(id: $id) {
                        title
                        author(language: "vi") {
                            name
                        }
                    }
                }
                """)
            .variable("id", "book-01")
            .execute()
            .path("book.author.name")
            .entity(String.class)
            .isEqualTo("Nguyen An");
    }
}
~~~

Nên có test cho các trường hợp:

1. Argument scalar được bind đúng kiểu Java.
2. Tên argument tường minh khác tên tham số Java vẫn hoạt động.
3. Input object bind vào record/DTO và các object lồng nhau.
4. @Arguments bind đủ các field, kể cả default value theo schema.
5. Argument bị omitted và explicit null được phân biệt khi dùng ArgumentValue.
6. Source object là kết quả đúng từ field cha.
7. @ContextValue nhận được dữ liệu do interceptor đưa vào context.
8. @LocalContextValue chỉ nhận dữ liệu được truyền trong nhánh tương ứng.
9. Principal phản ánh người dùng đã xác thực.
10. Binding error, Bean Validation error và business error được xử lý đúng.
11. @BatchMapping nhận source list và ánh xạ kết quả về đúng parent.

Với test context, có thể dùng GraphQlTester. Nếu cần kiểm tra HTTP header, authentication filter hoặc interceptor của transport, hãy bổ sung test bằng HttpGraphQlTester hoặc client phù hợp.

## 18. Những lỗi method argument resolution thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Argument luôn null | Tên trong @Argument không khớp SDL | Ghi tên argument tường minh |
| Không bind được record | Constructor component không khớp input field hoặc kiểu không tương thích | Kiểm tra tên và kiểu từng component |
| Không phân biệt được omitted và null | Dùng Java nullable field thông thường | Dùng ArgumentValue khi cần presence |
| Source object null hoặc sai kiểu | Parent resolver trả dữ liệu không đúng hoặc mapping đặt sai type | Kiểm tra output field cha và typeName |
| Map/DTO thiếu field | Nhầm @Argument với @Arguments hoặc client không gửi field | Chọn annotation đúng và kiểm tra variables |
| Context value không có | Interceptor chưa đưa key vào GraphQLContext | Kiểm tra context setup và tên key |
| Principal null | Request chưa xác thực hoặc transport không cung cấp principal | Kiểm tra security integration |
| Binding exception trước khi vào method | Giá trị không chuyển đổi được sang Java type | Kiểm tra scalar và DTO |
| Field con truy vấn dữ liệu lặp | Source resolver gọi repository từng object | Cân nhắc @BatchMapping/DataLoader |
| Service phụ thuộc GraphQL API | Truyền DataFetchingEnvironment sâu vào domain | Chuyển thành command/query thuần Java |

## 19. Quy trình thiết kế tham số cho handler method

Khi tạo một handler mới:

1. Xác định field GraphQL và arguments được khai báo trong SDL.
2. Dùng **@Argument** cho từng giá trị cần thiết hoặc **@Arguments** cho cả nhóm.
3. Dùng record/DTO cho input object có cấu trúc.
4. Chọn kiểu Java tương thích với scalar, enum, list và input type.
5. Với **@SchemaMapping**, nhận source object từ field cha.
6. Dùng **ArgumentValue** nếu cần phân biệt omitted với explicit null.
7. Dùng **@ContextValue**, **@LocalContextValue** hoặc Principal cho dữ liệu context phù hợp.
8. Chỉ dùng DataFetchingEnvironment khi cần thông tin execution ở mức thấp.
9. Áp dụng Bean Validation và xử lý binding error có chủ đích.
10. Chuyển input sang command/query để service không phụ thuộc GraphQL.
11. Với **@BatchMapping**, phân biệt source list với list argument của client.
12. Viết GraphQlTester cho binding, context, source và các trường hợp lỗi.

Method argument resolution là cầu nối giữa GraphQL execution và Java handler method. **@Argument** lấy dữ liệu client gửi; **@Arguments** bind toàn bộ arguments; source object cung cấp kết quả từ field cha; context và Principal mang metadata của request; DataFetchingEnvironment cho phép truy cập execution ở mức thấp. Khi chọn đúng resolver cho từng nguồn, dùng DTO có kiểu rõ ràng và kiểm thử các trường hợp null/omitted, handler sẽ dễ đọc hơn và service giữ được tính độc lập với GraphQL.
