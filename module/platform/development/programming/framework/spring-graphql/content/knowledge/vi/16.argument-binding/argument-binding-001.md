# @Argument

GraphQL field có thể nhận argument để client truyền mã định danh, điều kiện lọc, tùy chọn sắp xếp hoặc dữ liệu đầu vào cho một thao tác. Trong Spring for GraphQL, annotation **@Argument** giúp lấy một argument từ GraphQL execution context và bind giá trị đó vào tham số của phương thức controller. Nhờ vậy, resolver làm việc trực tiếp với kiểu Java như String, enum, record hoặc DTO thay vì tự đọc và ép kiểu dữ liệu từ request.

@Argument là một phần của cơ chế annotated controller. Nó thường đi cùng @QueryMapping, @MutationMapping hoặc @SchemaMapping. Để sử dụng hiệu quả, cần hiểu tên argument được xác định ra sao, GraphQL chuyển đổi kiểu ở bước nào, Spring bind input object vào Java như thế nào và cách xử lý khi client bỏ qua argument hoặc truyền null.

## @Argument làm nhiệm vụ gì?

Giả sử schema có field lấy sách theo ID:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
}
~~~

Client gọi field book và truyền argument id:

~~~graphql
query FindBook {
  book(id: "book-101") {
    id
    title
  }
}
~~~

Trong Spring for GraphQL, resolver nhận giá trị đó bằng @Argument:

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

Khi GraphQL thực thi field book, Spring lấy giá trị argument có tên id, chuyển đổi sang kiểu Java phù hợp rồi truyền vào tham số bookId. Tên biến Java có thể khác tên argument trong schema vì annotation đã chỉ rõ tên cần bind.

@Argument không phân tích toàn bộ GraphQL query và cũng không tự truy cập database. GraphQL Java chịu trách nhiệm parse và validate operation; Spring for GraphQL cung cấp cơ chế bind argument vào tham số Java; service thực hiện nghiệp vụ và truy cập dữ liệu.

## Tên argument được xác định như thế nào?

Có hai cách khai báo phổ biến:

~~~java
@QueryMapping
public Book book(@Argument("id") String bookId) {
    return bookService.findById(bookId);
}
~~~

Khai báo tên tường minh trong annotation phù hợp khi tên argument trong SDL khác tên tham số Java. Nếu hai tên giống nhau, có thể bỏ tên:

~~~java
@QueryMapping
public Book book(@Argument String id) {
    return bookService.findById(id);
}
~~~

Trong trường hợp bỏ tên, Spring dựa vào tên tham số Java để tìm argument tương ứng. Để cơ chế này hoạt động ổn định, ứng dụng cần giữ metadata tên tham số khi biên dịch Java, thường bằng tùy chọn compiler **-parameters**. Nếu metadata không có, Spring có thể không suy ra được tên tham số và việc bind sẽ thất bại.

Với API quan trọng hoặc khi tên Java khác tên schema, khai báo rõ tên như @Argument("id") giúp mapping dễ đọc và tránh phụ thuộc vào cấu hình compiler.

## Giá trị argument được chuyển đổi qua những bước nào?

Quá trình bind có thể hình dung theo luồng sau:

~~~mermaid
flowchart TD
    A["GraphQL document và variables"] --> B["GraphQL parse và validation"]
    B --> C["GraphQL scalar / enum coercion"]
    C --> D["Argument map trong DataFetchingEnvironment"]
    D --> E["@Argument trong annotated controller"]
    E --> F["GraphQlArgumentBinder"]
    F --> G["Tham số Java"]
    G --> H["Controller gọi service"]
~~~

GraphQL kiểm tra kiểu theo SDL và thực hiện coercion của scalar, enum hoặc custom scalar trước khi gọi resolver. Sau đó Spring for GraphQL bind các giá trị argument vào kiểu tham số Java. Với input object, binder có thể chuyển map lồng nhau thành record hoặc DTO tương ứng.

Điều này có nghĩa lỗi sai kiểu GraphQL và lỗi bind Java là hai loại vấn đề khác nhau:

- Nếu client truyền chuỗi vào argument Int, GraphQL có thể từ chối operation ở bước coercion trước khi resolver chạy.
- Nếu input object hợp lệ theo GraphQL nhưng không thể tạo Java object đích, lỗi xảy ra ở bước argument binding.
- Nếu bind thành công nhưng giá trị vi phạm quy tắc nghiệp vụ, service hoặc validation cần xử lý.

## Bind scalar và enum

Scalar GraphQL thường được bind vào kiểu Java tương ứng:

| GraphQL type | Kiểu Java thường dùng | Ví dụ |
| --- | --- | --- |
| ID | String | Mã sách |
| String | String | Từ khóa |
| Int | Integer hoặc int nếu chắc chắn không null | Số lượng |
| Float | Double | Giá trị số thực |
| Boolean | Boolean hoặc boolean nếu chắc chắn không null | Cờ bật/tắt |
| Custom scalar Date | LocalDate nếu scalar coercion trả về LocalDate | Ngày xuất bản |

Với argument nullable, nên dùng kiểu wrapper như Integer hoặc Boolean vì kiểu nguyên thủy int và boolean không thể biểu diễn null. Với argument non-null, GraphQL đã kiểm tra giá trị bắt buộc trước khi gọi resolver, nhưng kiểu wrapper vẫn hữu ích khi muốn chữ ký Java nhất quán.

Enum trong SDL có thể bind vào Java enum có tên hằng tương ứng:

~~~graphql
enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

type Query {
  books(status: BookStatus): [Book!]!
}
~~~

~~~java
public enum BookStatus {
    DRAFT,
    PUBLISHED,
    ARCHIVED
}

@QueryMapping
public List<Book> books(@Argument("status") BookStatus status) {
    return bookService.findByStatus(status);
}
~~~

Giá trị enum gửi từ client phải thuộc tập giá trị đã khai báo trong schema. Không nên dùng String cho enum chỉ vì muốn linh hoạt; kiểu enum giúp compiler và IDE hỗ trợ tốt hơn, đồng thời tránh các chuỗi trạng thái không hợp lệ.

## Bind custom scalar

Custom scalar được GraphQL Java coercion trước khi Spring bind argument. Vì vậy, kiểu Java của tham số cần tương thích với kiểu mà scalar trả về từ parseValue hoặc parseLiteral.

Ví dụ scalar Date đã được cấu hình để parse thành java.time.LocalDate:

~~~graphql
scalar Date

type Query {
  books(publishedAfter: Date): [Book!]!
}
~~~

Resolver có thể nhận LocalDate:

~~~java
@QueryMapping
public List<Book> books(@Argument("publishedAfter") LocalDate publishedAfter) {
    return bookService.findPublishedAfter(publishedAfter);
}
~~~

Nếu scalar Date được cấu hình để trả về String nhưng phương thức lại yêu cầu LocalDate, việc bind cần có converter phù hợp hoặc sẽ phát sinh lỗi chuyển đổi. Hãy giữ hợp đồng coercion và kiểu Java nhất quán để tránh chuyển đổi lặp lại ở nhiều tầng.

## Bind input object vào Java record

Khi một field nhận nhiều dữ liệu liên quan, schema thường gom chúng vào input object:

~~~graphql
input BookFilterInput {
  keyword: String
  authorId: ID
  status: BookStatus
  publishedAfter: Date
}

type Query {
  searchBooks(filter: BookFilterInput): [Book!]!
}
~~~

Có thể biểu diễn input object bằng Java record:

~~~java
public record BookFilter(
        String keyword,
        String authorId,
        BookStatus status,
        LocalDate publishedAfter) {
}
~~~

Resolver nhận toàn bộ input object:

~~~java
@QueryMapping
public List<Book> searchBooks(@Argument("filter") BookFilter filter) {
    return bookService.search(filter);
}
~~~

Spring for GraphQL dùng **GraphQlArgumentBinder** để chuyển dữ liệu input thành object đích. Binder hỗ trợ constructor binding và property binding, đồng thời xử lý cấu trúc lồng nhau. Với record, các thành phần của record được bind qua constructor; tên thành phần nên tương ứng với tên field trong input object.

Nếu argument filter có thể bị bỏ qua hoặc truyền null, tham số BookFilter có thể nhận null. Nếu muốn bắt buộc phải có object filter, khai báo filter: BookFilterInput! trong SDL. Cần phân biệt việc object bắt buộc phải tồn tại với việc từng field bên trong object có bắt buộc hay không.

## Bind input object vào POJO

Không bắt buộc dùng record. Có thể dùng class Java thông thường:

~~~java
public class BookFilter {

    private String keyword;
    private String authorId;
    private BookStatus status;

    public BookFilter() {
    }

    public String getKeyword() {
        return keyword;
    }

    public void setKeyword(String keyword) {
        this.keyword = keyword;
    }

    public String getAuthorId() {
        return authorId;
    }

    public void setAuthorId(String authorId) {
        this.authorId = authorId;
    }

    public BookStatus getStatus() {
        return status;
    }

    public void setStatus(BookStatus status) {
        this.status = status;
    }
}
~~~

Với POJO có constructor và setter phù hợp, binder có thể tạo object rồi gán các property tương ứng. Constructor binding phù hợp với kiểu bất biến như record; property binding hữu ích với JavaBean có setter. Nên chọn một kiểu dữ liệu nhất quán trong dự án để việc bind và validation dễ dự đoán.

## Đổi tên input field bằng @BindParam

Tên field trong GraphQL thường dùng camelCase, nhưng Java có thể dùng quy ước hoặc tên khác. Spring for GraphQL cung cấp **@BindParam** để chỉ rõ tên input field cần bind vào constructor parameter hoặc property.

Ví dụ schema dùng snake_case:

~~~graphql
input BookFilterInput {
  author_id: ID
  published_after: Date
}
~~~

Java record dùng camelCase:

~~~java
import org.springframework.graphql.data.method.annotation.BindParam;

public record BookFilter(
        @BindParam("author_id") String authorId,
        @BindParam("published_after") LocalDate publishedAfter) {
}
~~~

@BindParam giúp tách tên field công khai của GraphQL khỏi tên thuộc tính Java. Nếu schema và Java đã dùng cùng tên, không cần thêm annotation này. Hãy tránh đổi tên tùy tiện vì tên field input là một phần hợp đồng mà client đang sử dụng.

## Bind input object lồng nhau và danh sách

GraphQL input object có thể chứa object khác hoặc danh sách. Java model nên phản ánh cùng cấu trúc:

~~~graphql
input AuthorFilterInput {
  name: String
}

input BookFilterInput {
  keyword: String
  author: AuthorFilterInput
  statuses: [BookStatus!]
}

type Query {
  searchBooks(filter: BookFilterInput): [Book!]!
}
~~~

~~~java
public record AuthorFilter(String name) {
}

public record BookFilter(
        String keyword,
        AuthorFilter author,
        List<BookStatus> statuses) {
}
~~~

~~~java
@QueryMapping
public List<Book> searchBooks(@Argument BookFilter filter) {
    return bookService.search(filter);
}
~~~

Binder đi qua cấu trúc map đầu vào để tạo các object lồng nhau và danh sách tương ứng. Các kiểu generic nên được khai báo đầy đủ, chẳng hạn List<BookStatus>, để Spring có đủ thông tin chuyển đổi phần tử.

Nếu một object lồng nhau hoặc một phần tử danh sách không bind được, lỗi có thể xảy ra dù những field còn lại hợp lệ. Nên kiểm tra input theo từng cấp và trả thông báo validation dễ hiểu.

## Phân biệt argument bị bỏ qua và null bằng ArgumentValue

Với một argument nullable, tham số Java thông thường có thể nhận null trong cả hai trường hợp: client không gửi argument hoặc client gửi argument với giá trị null. Trong một số nghiệp vụ, hai trường hợp này có ý nghĩa khác nhau.

Ví dụ, với filter status:

- Bỏ qua status có nghĩa là không lọc theo trạng thái.
- Truyền status: null có thể có nghĩa là tìm các bản ghi chưa có trạng thái.
- Truyền status: PUBLISHED có nghĩa là chỉ lấy bản ghi đã xuất bản.

Spring for GraphQL cung cấp **ArgumentValue<T>** để giữ thông tin argument có bị bỏ qua hay không:

~~~java
import org.springframework.graphql.data.ArgumentValue;
import org.springframework.graphql.data.method.annotation.Argument;

@QueryMapping
public List<Book> books(
        @Argument("status") ArgumentValue<BookStatus> status) {

    if (status.isOmitted()) {
        return bookService.findWithoutStatusFilter();
    }

    if (status.value() == null) {
        return bookService.findBooksWithNullStatus();
    }

    return bookService.findByStatus(status.value());
}
~~~

ArgumentValue hữu ích khi resolver cần phân biệt omitted và explicit null. Nếu schema khai báo default value, GraphQL có thể áp dụng default trước khi gọi resolver; hãy xác định rõ hợp đồng default và kiểm thử hành vi thực tế của argument đó.

## Dùng @Argument trong @SchemaMapping

Argument không chỉ xuất hiện ở Query hoặc Mutation root. Field của object type cũng có thể nhận argument. Ví dụ, client yêu cầu số lượng review tối đa của một quyển sách:

~~~graphql
type Book {
  id: ID!
  title: String!
  reviews(first: Int = 10): [Review!]!
}
~~~

Resolver nhận cả source object và argument:

~~~java
@Controller
public class BookFieldController {

    private final ReviewService reviewService;

    public BookFieldController(ReviewService reviewService) {
        this.reviewService = reviewService;
    }

    @SchemaMapping(typeName = "Book", field = "reviews")
    public List<Review> reviews(
            Book book,
            @Argument("first") Integer first) {
        return reviewService.findByBookId(book.id(), first);
    }
}
~~~

Tham số Book là source object mà GraphQL đang phân giải; tham số được đánh dấu @Argument lấy giá trị first của field reviews. Khi một phương thức nhận nhiều loại dữ liệu, annotation giúp Spring phân biệt argument với source object và các tham số đặc biệt khác.

## Nhận Map khi cần cấu trúc linh hoạt

Nếu không muốn tạo DTO cho một input object đơn giản hoặc cấu trúc thật sự linh hoạt, có thể bind argument thành Map:

~~~java
@QueryMapping
public List<Book> searchBooks(
        @Argument("filter") Map<String, Object> filter) {
    return bookService.search(filter);
}
~~~

Map giúp truy cập key động nhưng mất nhiều lợi ích của kiểu tĩnh. Code phải tự kiểm tra key tồn tại, kiểu giá trị và cấu trúc lồng nhau. Với schema ổn định, record hoặc DTO thường an toàn và dễ bảo trì hơn.

Không nên nhận toàn bộ input thành Map chỉ để né việc thiết kế model. Một kiểu Java rõ ràng giúp compiler phát hiện sai tên field, IDE hỗ trợ refactor và validation có thể gắn trực tiếp lên property.

## Lỗi binding và cách xử lý

Spring GraphQL argument binder có thể phát hiện lỗi khi không thể chuyển đổi hoặc tạo object đích. Các lỗi thường gặp:

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Tham số nhận null | Tên @Argument không khớp tên argument trong SDL | Kiểm tra tên và khai báo tường minh |
| Không tìm được tên tham số | Thiếu metadata tên tham số khi bỏ tên trong @Argument | Dùng tên tường minh hoặc bật -parameters |
| Không tạo được record | Tên/thứ tự/thành phần constructor không phù hợp dữ liệu | Đối chiếu input field với record component |
| Field lồng nhau không bind | Kiểu Java không phản ánh cấu trúc input | Kiểm tra nested DTO và generic type |
| Sai kiểu scalar | GraphQL input không đúng scalar hoặc converter không phù hợp | Kiểm tra SDL, custom scalar coercion và Java target type |
| Enum không hợp lệ | Giá trị gửi lên không có trong enum schema | Dùng đúng enum value đã công bố |
| Omitted và null bị coi như nhau | Tham số chỉ là kiểu nullable thông thường | Dùng ArgumentValue khi cần phân biệt |

Lỗi coercion của GraphQL thường xuất hiện trước khi resolver được gọi. Lỗi bind Java xảy ra khi GraphQL đã có giá trị argument nhưng Spring không thể chuyển nó sang kiểu đích. Lỗi nghiệp vụ xảy ra sau khi bind thành công và cần được xử lý ở service hoặc validation layer.

Không nên bắt mọi lỗi binding rồi âm thầm thay bằng object rỗng. Làm như vậy có thể khiến resolver thực hiện truy vấn với điều kiện mặc định ngoài ý muốn. Hãy trả lỗi phù hợp và giữ thông tin chẩn đoán ở log server mà không để lộ dữ liệu nhạy cảm cho client.

## Validation sau khi bind

Bind thành công chỉ chứng minh dữ liệu có thể được chuyển thành kiểu Java. Nó không chứng minh dữ liệu hợp lệ theo nghiệp vụ. Ví dụ, quantity có thể bind thành Integer nhưng giá trị âm vẫn không hợp lệ; khoảng năm bắt đầu và kết thúc có thể đều là số nguyên nhưng quan hệ giữa chúng có thể sai.

Có thể kết hợp Jakarta Bean Validation với input DTO:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record BookSearchInput(
        @NotBlank @Size(max = 100) String keyword,
        @Min(1) @Max(100) Integer size) {
}
~~~

~~~java
import jakarta.validation.Valid;

@MutationMapping
public Book createBook(@Argument @Valid CreateBookInput input) {
    return bookService.create(input);
}
~~~

Validation cần dependency và cấu hình phù hợp, chẳng hạn Spring Boot validation starter. Tùy phiên bản Spring GraphQL và cách cấu hình method validation, lỗi có thể được biểu diễn qua exception validation hoặc binding exception. Hãy chuẩn hóa chúng thành GraphQL error có thông báo rõ ràng và không tiết lộ chi tiết nội bộ.

Các quy tắc liên quan đến dữ liệu hiện tại như người dùng có quyền sửa bản ghi hay không, mã tác giả có tồn tại không hoặc tenant có được phép truy cập không vẫn nên được kiểm tra ở service hoặc tầng domain.

## Kiểm thử @Argument

Spring for GraphQL cung cấp GraphQlTester để kiểm tra argument binding thông qua operation thật:

~~~java
graphQlTester.document("""
        query FindBook($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
    .variable("id", "book-101")
    .execute()
    .path("book.id")
    .entity(String.class)
    .isEqualTo("book-101");
~~~

Với input object, có thể truyền variables dạng Map:

~~~java
graphQlTester.document("""
        query Search($filter: BookFilterInput) {
            searchBooks(filter: $filter) {
                id
                title
            }
        }
        """)
    .variable("filter", Map.of(
            "keyword", "Spring",
            "status", "PUBLISHED"))
    .execute()
    .path("searchBooks")
    .entityList(Book.class)
    .hasSize(2);
~~~

Nên kiểm thử cả:

- Argument scalar và enum hợp lệ.
- Tên argument tường minh khác tên tham số Java.
- Input object bind vào record hoặc POJO.
- Input object lồng nhau và danh sách.
- Custom scalar chuyển đổi sang đúng kiểu Java.
- Argument nullable bị bỏ qua hoặc được truyền null.
- Argument non-null bị thiếu hoặc truyền null.
- Giá trị bind được nhưng vi phạm validation nghiệp vụ.
- Lỗi binding được chuyển thành GraphQL error phù hợp.

Khi cần xác minh toàn bộ HTTP transport, có thể dùng HttpGraphQlTester kết hợp WebTestClient. Còn với unit test service, nên kiểm thử logic nghiệp vụ độc lập với GraphQL binding.

## Nguyên tắc sử dụng @Argument

Khi viết annotated controller, hãy lưu ý:

1. **Đồng bộ tên với SDL.** Dùng @Argument("name") khi tên Java khác tên argument hoặc muốn mapping tường minh.
2. **Chọn kiểu Java phù hợp.** Dùng wrapper cho giá trị nullable, enum cho enum và record/DTO cho input object.
3. **Giữ cấu trúc input nhất quán.** Nested input và danh sách nên có Java model tương ứng.
4. **Hiểu GraphQL coercion trước binding.** Custom scalar phải trả về kiểu Java mà tham số có thể nhận.
5. **Dùng @BindParam khi cần đổi tên.** Giữ public schema độc lập với quy ước tên property Java.
6. **Dùng ArgumentValue đúng lúc.** Chỉ cần khi nghiệp vụ phân biệt argument bị bỏ qua với explicit null.
7. **Validation ở server.** Bind thành công không thay thế validation và authorization.
8. **Ưu tiên kiểu tĩnh.** Dùng Map cho dữ liệu động thật sự, không dùng để né model.
9. **Kiểm thử qua operation.** Xác minh cả binding thành công, coercion error và validation error.

@Argument là cầu nối giữa argument trong GraphQL schema và tham số Java của annotated controller. GraphQL Java chịu trách nhiệm parse, validate và coercion; Spring for GraphQL dùng GraphQlArgumentBinder để tạo giá trị Java; controller gọi service để xử lý nghiệp vụ. Khi tên, kiểu dữ liệu và cấu trúc input được thiết kế nhất quán, resolver sẽ dễ đọc, dễ kiểm thử và ít lỗi chuyển đổi hơn.
