# Argument mặc định

Một GraphQL field thường nhận arguments để lọc, phân trang hoặc điều khiển cách lấy dữ liệu. Client có thể truyền đầy đủ arguments trong mỗi request, nhưng nhiều API có một cách xử lý mặc định hợp lý: danh sách lấy 20 phần tử, sắp xếp theo thời gian mới nhất hoặc chỉ trả về sách đã xuất bản.

GraphQL SDL cho phép khai báo **default value** ngay trên argument. Khi client bỏ qua argument, GraphQL sử dụng giá trị mặc định trước khi gọi resolver. Cơ chế tương tự cũng có ở biến của operation và field bên trong input object. Hiểu đúng sự khác nhau giữa bỏ qua giá trị và truyền `null` là điều quan trọng khi xây dựng API bằng Spring for GraphQL, đặc biệt với filter và mutation cập nhật từng phần.

Bài học này giải thích cách khai báo default value, thứ tự áp dụng giữa variable default và argument default, hành vi với `null`, cách Spring bind giá trị vào `@Argument`, cùng cách kiểm thử các trường hợp đó.

## 1. Khai báo default value cho field argument

Default value được khai báo sau kiểu của argument bằng dấu `=`. Ví dụ:

```graphql
type Query {
  books(
    first: Int = 20
    offset: Int = 0
  ): [Book!]!
}
```

Client có thể gọi field mà không truyền argument:

```graphql
query {
  books {
    id
    title
  }
}
```

GraphQL áp dụng `first = 20` và `offset = 0` khi chuẩn bị arguments cho resolver. Client cũng có thể ghi đè giá trị mặc định:

```graphql
query {
  books(first: 5, offset: 10) {
    id
    title
  }
}
```

Trong request thứ hai, resolver nhận `first = 5` và `offset = 10`. Default value chỉ được sử dụng khi argument bị bỏ qua; nó không ép mọi request phải dùng giá trị mặc định.

Một schema đầy đủ hơn có thể khai báo default cho nhiều loại scalar và enum:

```graphql
enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

type Query {
  books(
    first: Int = 20
    offset: Int = 0
    status: BookStatus = PUBLISHED
    includeSummary: Boolean = false
  ): [Book!]!
}
```

Các giá trị mặc định ở trên là một phần của schema. Client có thể xem chúng qua introspection và các công cụ phát triển GraphQL có thể hiển thị chúng trong tài liệu API.

## 2. Các dạng giá trị mặc định hợp lệ

Default value trong SDL là một GraphQL constant value. Có thể dùng các dạng literal phù hợp với kiểu khai báo:

| Kiểu dữ liệu | Ví dụ default value |
| --- | --- |
| `Int` | `first: Int = 20` |
| `Float` | `minimumScore: Float = 4.5` |
| `String` | `keyword: String = "GraphQL"` |
| `Boolean` | `includeArchived: Boolean = false` |
| `ID` | `ownerId: ID = "user-100"` |
| Enum | `status: BookStatus = PUBLISHED` |
| List | `statuses: [BookStatus!] = [PUBLISHED, ARCHIVED]` |
| Input object | `filter: BookFilter = { status: PUBLISHED }` |

Ví dụ kết hợp:

```graphql
input BookFilter {
  keyword: String
  status: BookStatus
  includeArchived: Boolean
}

type Query {
  searchBooks(
    filter: BookFilter = {
      status: PUBLISHED
      includeArchived: false
    }
    first: Int = 20
  ): [Book!]!
}
```

Giá trị mặc định phải tương thích với kiểu của argument hoặc input field. Nếu khai báo `first: Int = "twenty"`, schema không hợp lệ vì chuỗi không thể dùng làm giá trị mặc định của `Int`.

Default value trong SDL không phải biểu thức Java. Bạn không thể gọi method, đọc environment variable, tham chiếu field khác hoặc tính giá trị theo thời gian. Ví dụ sau không hợp lệ:

```graphql
type Query {
  # Không hợp lệ: GraphQL SDL không thực thi biểu thức.
  books(first: Int = calculateDefaultPageSize()): [Book!]!
}
```

Nếu giá trị mặc định phụ thuộc tenant, người dùng hiện tại, cấu hình triển khai hoặc thời điểm request, hãy xử lý ở tầng ứng dụng thay vì cố đưa logic động vào SDL.

## 3. Phân biệt argument bị bỏ qua và argument nhận null

Đây là quy tắc quan trọng nhất khi làm việc với default value:

- Nếu client **không gửi argument**, GraphQL sử dụng default value nếu có.
- Nếu client **gửi argument với giá trị `null`**, giá trị `null` được giữ nguyên đối với argument nullable; default value không được áp dụng.
- Nếu argument có kiểu non-null, client không thể truyền `null` hợp lệ.

Ví dụ:

```graphql
type Query {
  books(first: Int = 20): [Book!]!
}
```

| Request | Giá trị resolver nhận |
| --- | --- |
| `{ books { id } }` | `first = 20` |
| `{ books(first: 5) { id } }` | `first = 5` |
| `{ books(first: null) { id } }` | `first = null` |

Nếu resolver hoặc service cần một số nguyên để phân trang, phải quyết định rõ cách xử lý trường hợp `null`. Không nên mặc định rằng `Int = 20` có nghĩa mọi trường hợp đều nhận 20.

### Non-null argument có default value

GraphQL cho phép khai báo non-null argument có default value:

```graphql
type Query {
  books(first: Int! = 20): [Book!]!
}
```

Client có thể bỏ qua `first` vì schema đã cung cấp giá trị mặc định. Nhưng nếu client truyền `null`, request không hợp lệ vì kiểu `Int!` không chấp nhận null. Resolver vì thế nhận một giá trị khác null khi field được thực thi hợp lệ.

Khác biệt này hữu ích khi API luôn cần một giá trị, nhưng muốn client có thể bỏ qua argument trong trường hợp phổ biến. Một non-null argument không có default value là argument bắt buộc:

```graphql
type Query {
  book(id: ID!): Book
}
```

## 4. Default value của variable trong operation

GraphQL operation cũng có thể khai báo giá trị mặc định cho variable. Cú pháp đặt default sau kiểu variable:

```graphql
query BookList($first: Int = 10) {
  books(first: $first) {
    id
    title
  }
}
```

Nếu client không gửi variable `first`, GraphQL sử dụng giá trị `10` đã khai báo trong operation. Client vẫn có thể truyền giá trị khác qua payload variables:

```json
{
  "first": 5
}
```

Khi đó query lấy 5 sách. Variable default thuộc về operation của client, còn argument default thuộc về schema của server. Hai nơi này phục vụ hai mục đích khác nhau:

| Loại default | Được khai báo ở đâu? | Ai kiểm soát? | Mục đích |
| --- | --- | --- | --- |
| Argument default | SDL của server | API/schema owner | Hành vi mặc định của field cho mọi client |
| Variable default | GraphQL operation | Client/query author | Giá trị mặc định riêng cho operation đó |

### Thứ tự áp dụng khi có cả hai default

Giả sử schema khai báo:

```graphql
type Query {
  books(first: Int = 20): [Book!]!
}
```

Operation khai báo variable default:

```graphql
query BookList($first: Int = 5) {
  books(first: $first) {
    id
    title
  }
}
```

Nếu client bỏ qua variable `first`, operation sử dụng `5`. Giá trị này được truyền vào argument `books(first:)`, vì vậy default `20` trong schema không còn được dùng.

Nếu operation không khai báo variable default:

```graphql
query BookList($first: Int) {
  books(first: $first) {
    id
    title
  }
}
```

Khi client bỏ qua variable `first`, argument được xem là không được cung cấp và default của schema là `20` được áp dụng. Nếu client gửi `{"first": null}`, giá trị null được truyền vào argument nullable và ghi đè cả hai default.

Có thể ghi nhớ thứ tự như sau:

1. Nếu client cung cấp variable, dùng giá trị đó, kể cả `null` nếu kiểu cho phép.
2. Nếu variable bị bỏ qua nhưng operation có variable default, dùng variable default.
3. Nếu argument vẫn không được cung cấp, dùng argument default trong schema nếu có.
4. Nếu không có default nào, argument nullable nhận `null`; argument non-null không có default khiến request không hợp lệ.

## 5. Default value cho field trong input object

Input field cũng có thể có default value. Điều này thường hữu ích với filter hoặc input object có nhiều thuộc tính tùy chọn:

```graphql
input BookFilter {
  keyword: String
  status: BookStatus = PUBLISHED
  includeArchived: Boolean = false
}

type Query {
  searchBooks(filter: BookFilter = {}): [Book!]!
}
```

Với schema trên, các request có hành vi khác nhau:

```graphql
# filter bị bỏ qua: argument default {} được sử dụng.
query {
  searchBooks {
    id
  }
}

# filter được truyền object rỗng: default của từng input field được áp dụng.
query {
  searchBooks(filter: {}) {
    id
  }
}

# status được truyền tường minh: giá trị này ghi đè input field default.
query {
  searchBooks(filter: { status: ARCHIVED }) {
    id
  }
}

# status được truyền null: default PUBLISHED không được áp dụng.
query {
  searchBooks(filter: { status: null }) {
    id
  }
}
```

Ở ví dụ này, `filter` bị bỏ qua sẽ nhận default object `{}`. Sau đó, input coercion áp dụng default `PUBLISHED` cho field `status` và `false` cho `includeArchived`. Nếu `filter` được truyền là `null`, toàn bộ input object là null; các default bên trong object không được áp dụng.

Default ở cấp argument và default ở cấp input field có thể được dùng cùng nhau, nhưng cần mô tả rõ để client hiểu hành vi. Đừng dùng default object lớn nếu nó khiến client khó biết server đang áp dụng những điều kiện lọc nào.

## 6. Default value và cập nhật từng phần

Mutation cập nhật từng phần thường cần phân biệt ba trạng thái của một input field:

1. Client không gửi field: giữ nguyên dữ liệu cũ.
2. Client gửi field với `null`: xóa giá trị nếu nghiệp vụ cho phép.
3. Client gửi giá trị cụ thể: cập nhật bằng giá trị đó.

Nếu đặt default value cho input field trong một mutation kiểu partial update, trường hợp bị bỏ qua có thể bị thay bằng default trước khi resolver nhận input. Khi đó server mất thông tin rằng client đã không gửi field.

Ví dụ không phù hợp cho partial update:

```graphql
input UpdateBookInput {
  title: String = "Untitled"
  summary: String
}
```

Nếu client gửi `{ summary: "Mô tả mới" }`, input coercion có thể điền `title = "Untitled"`. Resolver khó phân biệt client muốn đổi title thành giá trị mặc định hay chỉ muốn cập nhật summary. Với input dùng để cập nhật từng phần, thường nên tránh default cho những field cần giữ nguyên khi bị bỏ qua.

### Phân biệt omitted và null trong Spring for GraphQL

Spring for GraphQL cung cấp `ArgumentValue<T>` để phân biệt giá trị bị bỏ qua với giá trị null tường minh trong argument binding:

```java
import org.springframework.graphql.data.ArgumentValue;

@MutationMapping
public Book updateBook(
        @Argument("id") String id,
        @Argument("summary") ArgumentValue<String> summary) {

    if (summary.isOmitted()) {
        return bookService.updateWithoutChangingSummary(id);
    }

    if (summary.value() == null) {
        return bookService.clearSummary(id);
    }

    return bookService.updateSummary(id, summary.value());
}
```

`ArgumentValue` hữu ích khi API có semantics cập nhật từng phần. Với argument có default value, GraphQL đã áp dụng default trước khi resolver nhận giá trị; do đó không nên đặt default nếu mục tiêu là giữ trạng thái omitted để phân biệt trong mutation.

## 7. Spring for GraphQL nhận default value qua @Argument

Trong Spring for GraphQL, GraphQL Java thực hiện coercion và áp dụng default theo schema/operation trước khi Spring bind argument vào method handler. Vì vậy controller thường nhận giá trị đã được áp dụng default.

Schema:

```graphql
enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

type Query {
  books(
    first: Int = 20
    offset: Int = 0
    status: BookStatus = PUBLISHED
  ): [Book!]!
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
    public List<Book> books(
            @Argument("first") Integer first,
            @Argument("offset") Integer offset,
            @Argument("status") BookStatus status) {

        return bookService.findBooks(first, offset, status);
    }
}
```

Với query `{ books { id title } }`, method nhận `20`, `0` và `BookStatus.PUBLISHED`. Nếu client gửi `first: null`, tham số `Integer first` có thể nhận null vì argument được khai báo nullable. Dùng wrapper `Integer` thay vì primitive `int` khi schema cho phép null.

### Default trong SDL và default trong Java

Không nhầm default value của schema với fallback trong method Java:

```java
@QueryMapping
public List<Book> books(@Argument("first") Integer first) {
    int effectiveFirst = first == null ? 20 : first;
    return bookService.findBooks(effectiveFirst);
}
```

Đoạn Java trên đặt fallback khi resolver nhận null. Nó không làm cho schema hiển thị default `20` trong introspection và không thay đổi validation của GraphQL. Nếu muốn default là một phần hợp đồng công khai, hãy khai báo trong SDL:

```graphql
type Query {
  books(first: Int = 20): [Book!]!
}
```

Fallback trong Java vẫn có thể cần thiết cho logic nội bộ, nhưng hãy tránh để default ở schema và default trong code mâu thuẫn nhau. Khi hai nơi có giá trị khác nhau, client nhìn thấy một hợp đồng nhưng server có thể xử lý theo quy tắc khác.

### Kotlin và giá trị tham số mặc định

Kotlin cho phép khai báo default parameter trong method:

```kotlin
@QueryMapping
fun books(@Argument first: Int = 20): List<Book> =
    bookService.findBooks(first)
```

Default parameter của Kotlin là cơ chế ngôn ngữ ở phía server. Nó không tự trở thành default value trong GraphQL schema và không xuất hiện trong introspection. Nếu muốn client thấy default trong tài liệu API, vẫn khai báo `first: Int = 20` trong SDL. Đồng thời kiểm tra cách Spring bind argument vào Kotlin method với phiên bản Spring GraphQL và Kotlin đang dùng.

## 8. Kiểm thử default value

Khi kiểm thử, cần bao phủ cả trường hợp omitted, giá trị tường minh và null. `GraphQlTester` có thể gửi document và variables như client thật.

Ví dụ kiểm tra argument default:

```java
@GraphQlTest(BookQueryController.class)
class BookQueryControllerTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockBean
    BookService bookService;

    @Test
    void appliesSchemaDefaultsWhenArgumentsAreOmitted() {
        given(bookService.findBooks(20, 0, BookStatus.PUBLISHED))
                .willReturn(List.of());

        graphQlTester.document("""
                query {
                    books {
                        id
                        title
                    }
                }
                """)
                .execute()
                .path("books")
                .entityList(Book.class)
                .hasSize(0);

        then(bookService).should()
                .findBooks(20, 0, BookStatus.PUBLISHED);
    }
}
```

Ví dụ rút gọn này giả định service và kiểu `Book` của dự án có chữ ký tương ứng. Có thể thêm test cho:

- Gửi `first: 5` để xác nhận giá trị client ghi đè default.
- Gửi `first: null` để xác nhận nullable argument nhận null.
- Bỏ variable có default trong operation để xác nhận variable default được dùng.
- Bỏ variable không có default để xác nhận argument default trong schema được dùng.
- Gửi input object rỗng để xác nhận input field defaults.
- Gửi input field null để xác nhận null tường minh không bị thay bằng default.
- Bỏ input field trong mutation partial update để xác nhận trạng thái omitted được giữ lại khi không có default.

Nếu muốn kiểm tra default value đã công khai trong schema, dùng introspection:

```graphql
query BooksArgumentDefaults {
  __type(name: "Query") {
    fields {
      name
      args {
        name
        defaultValue
      }
    }
  }
}
```

`defaultValue` trong introspection được biểu diễn dưới dạng GraphQL literal dạng chuỗi, ví dụ `20`, `PUBLISHED` hoặc `{status: PUBLISHED}`. Nó không phải JSON value đã được resolver nhận.

## 9. Lỗi thường gặp khi dùng default value

| Biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Resolver nhận null dù đã khai báo default | Client truyền `null` tường minh | Kiểm tra request và phân biệt omitted với null |
| Default của schema không được dùng | Variable default trong operation đã cung cấp giá trị | Kiểm tra khai báo variable và payload variables |
| Schema không khởi động | Literal default không tương thích kiểu argument/input field | Kiểm tra kiểu và cú pháp GraphQL constant value |
| Resolver nhận giá trị khác mong đợi | Có default ở nhiều tầng: variable, argument, input field và Java | Xác định tầng nào đã cung cấp giá trị trước khi resolver chạy |
| Mutation partial update vô tình ghi đè field | Input field có default khiến omitted trở thành giá trị mặc định | Bỏ default cho field cần giữ semantics omitted/null/value |
| Introspection không hiển thị default | Chưa khai báo default trong SDL hoặc đang kiểm tra sai argument | Truy vấn `__type`, `fields`, `args` và `defaultValue` |
| Dùng `int` gây lỗi khi argument nullable | Java primitive không biểu diễn null | Dùng `Integer` hoặc kiểu nullable phù hợp |

## 10. Nguyên tắc thiết kế default value

- Đặt default trong SDL khi đó là hành vi công khai, ổn định và có ý nghĩa giống nhau với mọi client.
- Dùng variable default khi giá trị mặc định chỉ thuộc về một operation cụ thể của client.
- Dùng default cho pagination, sort hoặc filter nếu có lựa chọn mặc định hợp lý và dễ dự đoán.
- Chỉ đặt default trên non-null argument khi server có thể luôn cung cấp giá trị đó nếu client bỏ qua argument.
- Hiểu rõ `null` khác với omitted. Với nullable argument, `null` tường minh sẽ ghi đè default.
- Tránh default cho input field của mutation partial update nếu cần phân biệt client không gửi field với client muốn cập nhật thành một giá trị cụ thể.
- Không đặt logic động như tenant hiện tại, người dùng hiện tại, ngày hiện tại hoặc cấu hình môi trường trong SDL default.
- Không duy trì hai giá trị mặc định khác nhau giữa SDL, Java/Kotlin và service layer.
- Viết description cho default có ý nghĩa nghiệp vụ để client hiểu khi nào giá trị được áp dụng.
- Kiểm thử omitted, explicit value, explicit null và variable default riêng biệt.

## 11. Bài tập thực hành

Cho schema quản lý sách:

```graphql
enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

input BookFilter {
  keyword: String
  status: BookStatus = PUBLISHED
  includeArchived: Boolean = false
}

type Query {
  books(
    filter: BookFilter = {}
    first: Int = 20
    offset: Int = 0
  ): [Book!]!
}
```

Hãy trả lời và kiểm chứng:

1. Resolver nhận những giá trị nào khi client gọi `{ books { id } }`?
2. Nếu client gọi `books(filter: {})`, input field defaults được áp dụng ra sao?
3. Nếu client gọi `books(filter: { status: null })`, resolver nhận giá trị status nào?
4. Nếu operation khai báo `$first: Int = 5` và schema khai báo `first: Int = 20`, giá trị nào được sử dụng khi client không gửi variable?
5. Nếu client gửi `first: null`, điều gì xảy ra?
6. Vì sao không nên đặt default `title: String = "Untitled"` trong input của mutation cập nhật từng phần?

Sau đó viết test `GraphQlTester` xác nhận các trường hợp omitted, explicit value và explicit null. Cuối cùng, dùng introspection kiểm tra default value mà schema công khai cho client.

Khi hoàn thành, bạn cần phân biệt được ba nơi có thể đặt default: variable của operation, argument của field và field trong input object. GraphQL áp dụng default theo quy tắc coercion trước khi resolver Spring for GraphQL nhận dữ liệu; hiểu rõ omitted và null sẽ giúp API có hành vi ổn định, nhất là khi xử lý filter và mutation cập nhật từng phần.
