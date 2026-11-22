# Query có argument

Trong GraphQL, một field có thể nhận **argument** để client truyền điều kiện lọc, mã định danh, thứ tự sắp xếp hoặc giới hạn số lượng dữ liệu. Nhờ argument, một field có thể phục vụ nhiều tình huống truy vấn mà không cần tạo một Query field riêng cho từng biến thể. Ví dụ, field books có thể trả về danh sách sách theo từ khóa, tác giả, trạng thái xuất bản và thông tin phân trang.

Trong Spring for GraphQL, phương thức xử lý Query nhận giá trị argument bằng annotation **@Argument**. Spring đọc dữ liệu từ GraphQL operation, chuyển đổi sang kiểu Java tương ứng rồi truyền vào phương thức controller. Vì vậy, cần thiết kế argument trong SDL rõ ràng và bảo đảm kiểu Java tương thích với hợp đồng đó.

## Argument trong GraphQL là gì?

Argument là tham số được khai báo ngay sau tên field trong schema. Mỗi argument có tên, kiểu dữ liệu và có thể có giá trị mặc định:

~~~graphql
enum BookSort {
  TITLE_ASC
  PUBLISHED_DESC
  RATING_DESC
}

type Query {
  book(id: ID!): Book
  books(authorId: ID, limit: Int = 20, sort: BookSort = TITLE_ASC): [Book!]!
}

type Book {
  id: ID!
  title: String!
}
~~~

Trong ví dụ:

- Field book nhận argument id có kiểu ID!; client bắt buộc truyền mã sách.
- Field books nhận authorId tùy chọn để lọc theo tác giả.
- Argument limit có giá trị mặc định 20 nếu client không truyền giá trị.
- Giá trị argument được sử dụng để quyết định dữ liệu mà resolver trả về.

Argument thuộc về từng field. Client có thể truyền các giá trị khác nhau khi gọi cùng một field ở những vị trí khác nhau trong một operation. Nếu cần gọi cùng field nhiều lần trong cùng selection set, hãy dùng alias để đặt tên riêng cho từng kết quả:

~~~graphql
query {
  newest: books(limit: 5, sort: PUBLISHED_DESC) {
    id
    title
  }
  popular: books(limit: 5, sort: RATING_DESC) {
    id
    title
  }
}
~~~

Hai lời gọi trên cùng sử dụng field books nhưng có argument và alias khác nhau. Response sẽ có hai key newest và popular.

## Chọn kiểu dữ liệu cho argument

Argument có thể dùng các input type hợp lệ của GraphQL, chẳng hạn scalar, enum, input object hoặc danh sách của những kiểu đó. Object type, interface và union là output type nên không thể dùng trực tiếp làm kiểu argument.

Các kiểu thường gặp:

| Kiểu | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Scalar | id: ID!, keyword: String | Giá trị đơn như chuỗi, số, boolean |
| Enum | status: BookStatus | Một giá trị trong tập lựa chọn xác định |
| Input object | filter: BookFilterInput | Nhóm nhiều điều kiện có cấu trúc |
| List | ids: [ID!]! | Danh sách giá trị đầu vào |

Ví dụ khai báo enum và input object:

~~~graphql
enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

enum BookSort {
  TITLE_ASC
  PUBLISHED_DESC
  RATING_DESC
}

input BookFilterInput {
  keyword: String
  authorId: ID
  status: BookStatus
  publishedFrom: Int
  publishedTo: Int
}

type Query {
  books(
    filter: BookFilterInput
    sort: BookSort = TITLE_ASC
    page: Int = 0
    size: Int = 20
  ): [Book!]!
}
~~~

Input object giúp gom các điều kiện có liên quan thành một tham số. Khi API cần thêm điều kiện mới, có thể mở rộng BookFilterInput mà không phải tạo một danh sách argument dài trên field books. Tuy nhiên, input object vẫn là hợp đồng công khai; chỉ đưa vào những trường client thực sự được phép sử dụng.

## Nullability và giá trị mặc định

Dấu chấm than trong SDL quy định argument có bắt buộc hay không:

~~~graphql
type Query {
  book(id: ID!): Book
  books(keyword: String, limit: Int = 20): [Book!]!
}
~~~

- ID! nghĩa là client phải cung cấp id và giá trị không được null.
- String nghĩa là keyword có thể bị bỏ qua hoặc được truyền null.
- limit: Int = 20 nghĩa là khi client bỏ qua argument, GraphQL sử dụng giá trị mặc định 20.
- Nếu client truyền null tường minh cho limit, giá trị mặc định không được áp dụng; argument có kiểu Int nullable nên giá trị null có thể được chấp nhận.

Cần phân biệt ba trường hợp:

| Cách gửi | Ý nghĩa |
| --- | --- |
| Không gửi argument | Argument bị bỏ qua; GraphQL dùng default nếu có |
| Gửi argument với null | Client chủ động truyền giá trị null; default không thay thế |
| Gửi giá trị cụ thể | GraphQL kiểm tra kiểu và chuyển giá trị cho resolver |

Với argument non-null không có default, nếu client bỏ qua hoặc truyền null, operation bị lỗi validation/coercion trước khi resolver được gọi. Quy tắc này giúp server không phải xử lý một giá trị bắt buộc nhưng bị thiếu.

Default value được khai báo trong SDL là một phần của hợp đồng API. Hãy chọn giá trị mặc định có ý nghĩa nghiệp vụ và tránh dùng default khiến client vô tình tải quá nhiều dữ liệu.

## Truyền argument bằng GraphQL variables

Client có thể viết giá trị trực tiếp trong operation:

~~~graphql
query {
  book(id: "book-101") {
    id
    title
  }
}
~~~

Tuy nhiên, cách phổ biến hơn là khai báo variables để tách câu query khỏi dữ liệu đầu vào:

~~~graphql
query FindBook($id: ID!) {
  book(id: $id) {
    id
    title
  }
}
~~~

Variables được gửi riêng trong request JSON:

~~~json
{
  "operationName": "FindBook",
  "query": "query FindBook($id: ID!) { book(id: $id) { id title } }",
  "variables": {
    "id": "book-101"
  }
}
~~~

GraphQL kiểm tra kiểu của variable so với kiểu argument trong schema. Ví dụ, variable ID! tương thích với argument id: ID!. Nếu client gửi sai kiểu, operation bị từ chối trước khi resolver chạy.

Variables giúp tái sử dụng operation, tránh nối chuỗi để tạo query và thuận tiện cho caching operation ở client hoặc gateway. Giá trị đầu vào vẫn cần được validation theo quy tắc nghiệp vụ ở server.

## Nhận argument trong Spring for GraphQL bằng @Argument

Spring for GraphQL cung cấp annotation **@Argument** trong package annotated controller để bind argument của GraphQL field vào tham số Java:

~~~graphql
type Query {
  book(id: ID!): Book
}
~~~

~~~java
@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String bookId) {
        return bookService.findById(bookId);
    }
}
~~~

Argument trong SDL tên là id, còn tham số Java tên bookId. Khai báo @Argument("id") chỉ rõ tên cần bind. Nếu tên tham số Java trùng với tên argument và metadata tên tham số được giữ trong quá trình biên dịch, có thể viết ngắn thành @Argument String id.

Tên argument phải khớp với schema. Nếu SDL khai báo bookId nhưng Java lại bind id, Spring không tự đoán rằng hai tên đó có cùng ý nghĩa. Khi tên khác nhau, hãy chỉ rõ tên trong annotation để tránh nhận null hoặc lỗi binding.

## Bind nhiều argument vào một phương thức

Một resolver có thể nhận nhiều argument riêng biệt:

~~~graphql
type Query {
  searchBooks(
    keyword: String!
    limit: Int = 20
    status: BookStatus
  ): [Book!]!
}
~~~

~~~java
@QueryMapping
public List<Book> searchBooks(
        @Argument String keyword,
        @Argument Integer limit,
        @Argument BookStatus status) {
    return bookService.search(keyword, limit, status);
}
~~~

Spring chuyển từng argument sang kiểu Java tương ứng. Dùng kiểu wrapper như Integer khi argument có thể null; kiểu nguyên thủy int không biểu diễn được null. Nếu SDL bảo đảm argument luôn có giá trị nhờ dấu ! hoặc default value, service vẫn nên có giới hạn và quy tắc kiểm tra đầu vào rõ ràng.

Khi field có nhiều tham số liên quan, input object thường dễ quản lý hơn việc thêm nhiều argument rời rạc. Điều này đặc biệt hữu ích với bộ lọc tìm kiếm, cấu hình báo cáo hoặc điều kiện phân trang.

## Bind input object vào Java record hoặc DTO

Với input object trong SDL:

~~~graphql
input BookFilterInput {
  keyword: String
  authorId: ID
  status: BookStatus
  publishedFrom: Int
  publishedTo: Int
}

type Query {
  books(filter: BookFilterInput): [Book!]!
}
~~~

Có thể khai báo Java record tương ứng:

~~~java
public record BookFilterInput(
        String keyword,
        String authorId,
        BookStatus status,
        Integer publishedFrom,
        Integer publishedTo) {
}
~~~

Resolver nhận toàn bộ input object:

~~~java
@QueryMapping
public List<Book> books(@Argument BookFilterInput filter) {
    return bookService.findBooks(filter);
}
~~~

Spring for GraphQL sử dụng cơ chế argument binding để chuyển map dữ liệu đầu vào thành object Java. Record hoặc DTO cần có constructor/property phù hợp với cấu trúc input. Với input lồng nhau, kiểu Java tương ứng cũng cần mô tả đúng cấu trúc đó.

Nếu cần xử lý input linh hoạt hoặc cấu trúc thay đổi, có thể nhận Map:

~~~java
@QueryMapping
public List<Book> books(@Argument Map<String, Object> filter) {
    return bookService.findBooks(filter);
}
~~~

Map linh hoạt nhưng làm giảm lợi ích kiểm tra kiểu ở compile time và khiến việc validation thủ công phức tạp hơn. Với API ổn định, DTO hoặc record thường giúp hợp đồng Java rõ ràng và dễ kiểm thử.

## Phân biệt argument bị bỏ qua và argument null

Đối với một số nghiệp vụ cập nhật hoặc tìm kiếm, hai trường hợp bỏ qua argument và truyền null có ý nghĩa khác nhau. Ví dụ, client muốn lọc theo status:

- Bỏ qua status: không áp dụng bộ lọc trạng thái.
- Truyền status: null: có thể yêu cầu tìm những bản ghi chưa có trạng thái, nếu nghiệp vụ định nghĩa như vậy.
- Truyền status: PUBLISHED: chỉ lấy sách đã xuất bản.

Nếu tham số Java chỉ là BookStatus, cả omitted và explicit null có thể được bind thành null. Spring for GraphQL cung cấp **ArgumentValue<T>** để giữ thông tin argument có bị bỏ qua hay không:

~~~java
import org.springframework.graphql.data.ArgumentValue;

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

ArgumentValue giúp resolver phân biệt argument không xuất hiện trong operation với argument được gửi tường minh là null. Chỉ dùng cơ chế này khi sự khác biệt có ý nghĩa nghiệp vụ; với nhiều truy vấn thông thường, một tham số nullable là đủ.

## Validation argument

GraphQL kiểm tra kiểu dữ liệu, nullability và cấu trúc input theo schema. Nhưng schema không thể diễn đạt mọi quy tắc nghiệp vụ. Ví dụ, size có thể là Int nhưng ứng dụng cần giới hạn từ 1 đến 100; publishedFrom không được lớn hơn publishedTo; keyword không được chỉ chứa khoảng trắng.

Có thể dùng Jakarta Bean Validation trên input DTO khi dự án đã cấu hình validation:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Size;

public record BookSearchInput(
        @Size(max = 100) String keyword,
        @Min(1) @Max(100) Integer size) {
}
~~~

~~~graphql
input BookSearchInput {
  keyword: String
  size: Int
}

type Query {
  searchBooks(input: BookSearchInput!): [Book!]!
}
~~~

Resolver có thể đánh dấu tham số input với @Valid:

~~~java
@QueryMapping
public List<Book> searchBooks(@Argument @Valid BookSearchInput input) {
    return bookService.search(input);
}
~~~

Validation cần dependency và cấu hình phù hợp, chẳng hạn Spring Boot validation starter. Hãy kiểm tra cách phiên bản Spring for GraphQL của dự án kích hoạt validation trên method argument và chuẩn hóa lỗi validation thành GraphQL error có thông tin phù hợp cho client.

Không nên chỉ dựa vào validation ở client. Mọi giá trị từ request đều cần được kiểm tra ở server trước khi dùng trong service hoặc repository.

## Dùng argument cho lọc, sắp xếp và phân trang

Một Query field thực tế thường kết hợp filter, sort và pagination:

~~~graphql
enum BookSort {
  TITLE_ASC
  PUBLISHED_DESC
}

input BookFilterInput {
  keyword: String
  authorId: ID
  status: BookStatus
}

type Query {
  books(
    filter: BookFilterInput
    sort: BookSort = TITLE_ASC
    page: Int = 0
    size: Int = 20
  ): [Book!]!
}
~~~

Java resolver:

~~~java
@QueryMapping
public List<Book> books(
        @Argument BookFilterInput filter,
        @Argument BookSort sort,
        @Argument Integer page,
        @Argument Integer size) {

    int safePage = Math.max(page == null ? 0 : page, 0);
    int safeSize = Math.min(Math.max(size == null ? 20 : size, 1), 100);

    return bookService.findBooks(filter, sort, safePage, safeSize);
}
~~~

Resolver chuẩn hóa page và size để bảo vệ tầng dữ liệu khỏi giá trị âm hoặc kích thước quá lớn. Trong ứng dụng thực tế, nên đưa việc kiểm tra và chuẩn hóa này vào một thành phần dùng chung hoặc service để các endpoint áp dụng nhất quán.

Với danh sách rất lớn hoặc dữ liệu thường xuyên thay đổi, cursor pagination có thể phù hợp hơn offset pagination. Dù dùng cách nào, schema cần mô tả rõ đơn vị trang, giới hạn kích thước, thứ tự sắp xếp và cách xử lý cursor không hợp lệ.

## Argument và truy vấn dữ liệu an toàn

Argument thường được chuyển xuống service và repository để tạo điều kiện truy vấn. Không nối trực tiếp chuỗi keyword, sort hoặc filter vào câu SQL bằng phép cộng chuỗi. Hãy dùng parameter binding của repository hoặc query builder có hỗ trợ tham số để tránh SQL injection.

Với sort field, không nên nhận tên cột tùy ý từ client rồi ghép vào SQL. Hãy dùng enum như BookSort để giới hạn các lựa chọn hợp lệ, sau đó ánh xạ từng enum sang thuộc tính sắp xếp đã được cho phép.

Argument cũng có thể chứa dữ liệu nhạy cảm. Không ghi toàn bộ variables hoặc input object vào log nếu chúng có token, thông tin cá nhân hoặc dữ liệu bí mật. Cần kiểm tra quyền truy cập và phạm vi tenant ở service/repository, kể cả khi argument đã hợp lệ theo schema.

## Kiểm thử Query có argument

Spring for GraphQL cung cấp GraphQlTester để kiểm thử operation và variables. Ví dụ:

~~~java
graphQlTester.document("""
        query Books($filter: BookFilterInput, $size: Int) {
            books(filter: $filter, size: $size) {
                id
                title
            }
        }
        """)
    .variable("filter", Map.of(
            "keyword", "Spring",
            "status", "PUBLISHED"))
    .variable("size", 10)
    .execute()
    .path("books")
    .entityList(Book.class)
    .hasSize(2);
~~~

Nên kiểm thử các trường hợp:

- Argument hợp lệ và trả về dữ liệu đúng.
- Bỏ qua argument có default và xác nhận default được áp dụng.
- Truyền null vào argument nullable.
- Bỏ qua hoặc truyền null vào argument non-null và xác nhận lỗi trước resolver.
- Truyền sai scalar hoặc enum value.
- Input object thiếu field bắt buộc hoặc chứa giá trị không hợp lệ theo nghiệp vụ.
- Pagination có page âm, size bằng 0 hoặc size vượt giới hạn.
- Argument filter không được phép truy cập dữ liệu thuộc tenant khác.

Khi kiểm thử biến input object, có thể dùng Map hoặc DTO phù hợp với tester và cấu trúc schema. Test nên kiểm tra cả kết quả lẫn lỗi GraphQL, không chỉ xác nhận HTTP request được gửi thành công.

## Lỗi thường gặp khi bind argument

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Tham số Java nhận null | Tên @Argument không khớp SDL hoặc client không gửi giá trị | So sánh tên argument, variables và annotation |
| Không bind được input object | Record/DTO không tương thích field hoặc kiểu | Kiểm tra constructor, property và kiểu Java |
| Sai kiểu argument | Client gửi chuỗi cho Int hoặc enum không tồn tại | Sửa variable type và giá trị |
| Default không được dùng | Client truyền null tường minh | Phân biệt omitted và null |
| Không phân biệt omitted với null | Tham số Java nullable thông thường | Dùng ArgumentValue khi nghiệp vụ cần phân biệt |
| Truy vấn trả quá nhiều dữ liệu | Thiếu giới hạn pagination hoặc size không được kiểm tra | Đặt default và maximum ở server |
| Query bị lỗi trước khi resolver chạy | Argument non-null bị thiếu hoặc sai kiểu | Kiểm tra schema và variables |

## Nguyên tắc thiết kế argument

Khi thiết kế argument cho Query field, nên áp dụng những nguyên tắc sau:

1. **Đặt tên theo ý nghĩa nghiệp vụ.** Dùng id, keyword, filter hoặc pageSize rõ nghĩa và nhất quán.
2. **Chọn kiểu đúng với dữ liệu.** Dùng enum cho tập lựa chọn cố định và input object cho nhóm điều kiện có cấu trúc.
3. **Quy định nullability có chủ đích.** Chỉ dùng dấu ! khi client bắt buộc phải gửi giá trị và server cần giá trị đó.
4. **Đặt default hợp lý.** Default giúp operation ngắn hơn nhưng không được tạo tải dữ liệu lớn ngoài dự kiến.
5. **Dùng variables cho dữ liệu động.** Tách operation khỏi giá trị đầu vào và tránh nối chuỗi query.
6. **Bind vào DTO hoặc record.** Kiểu Java rõ ràng giúp service dễ kiểm tra và bảo trì.
7. **Validation ở server.** Kiểm tra giới hạn, quan hệ giữa các trường và quyền truy cập trước khi truy vấn dữ liệu.
8. **Giới hạn pagination.** Không để client yêu cầu số lượng bản ghi không giới hạn.
9. **Dùng ArgumentValue khi cần.** Phân biệt omitted và null nếu hai trường hợp có ý nghĩa khác nhau.

Query argument là cơ chế để client điều khiển cách lấy dữ liệu qua một hợp đồng có kiểu rõ ràng. Trong Spring for GraphQL, SDL định nghĩa tên, kiểu, nullability và default; @Argument chuyển dữ liệu sang Java; input DTO/record gom nhóm điều kiện; service và repository áp dụng validation, phân quyền và truy vấn an toàn. Thiết kế tốt giúp một Query field phục vụ nhiều nhu cầu mà vẫn dễ hiểu, dễ kiểm thử và kiểm soát được chi phí truy vấn.
