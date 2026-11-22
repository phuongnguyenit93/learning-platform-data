# Field argument trong GraphQL

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích field là gì và argument được khai báo, truyền vào field như thế nào.
- Đọc cú pháp định nghĩa field và argument trong GraphQL SDL.
- Phân biệt argument bắt buộc, nullable, có giá trị mặc định và argument nhận danh sách hoặc input object.
- Viết Query và Mutation sử dụng arguments bằng literal và variables.
- Hiểu cách arguments hoạt động trên cả root field lẫn nested field.
- Ánh xạ arguments vào method Java bằng `@Argument` và `@SchemaMapping` trong Spring for GraphQL.
- Xử lý input object, giá trị bị bỏ qua, giá trị null và lỗi đầu vào.
- Thiết kế arguments nhất quán cho filter, sort, pagination và bảo mật.

## 1. Field và argument là gì?

Field là đơn vị dữ liệu mà client yêu cầu trong một GraphQL operation. Mỗi field được khai báo trong một type của schema và có kiểu trả về. Field có thể có thêm arguments để client cung cấp thông tin đầu vào cho việc lấy giá trị đó.

Ví dụ:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

Trong khai báo trên:

- `book` là tên field.
- `id` là argument của field.
- `ID!` là kiểu của argument. Dấu `!` cho biết giá trị không được null.
- `Book` là kiểu trả về của field.

Client sử dụng field và argument trong operation:

~~~graphql
query {
    book(id: "book-42") {
        id
        title
    }
}
~~~

Client yêu cầu field `book` và truyền argument `id` với giá trị `"book-42"`. Vì `book` trả về object `Book`, operation tiếp tục chọn các field con `id` và `title`.

Có thể hiểu đơn giản:

- **Schema định nghĩa** field nào tồn tại, field nhận những argument nào, kiểu dữ liệu của chúng và field trả về kiểu gì.
- **Operation truyền** giá trị cụ thể cho các argument và chọn những field cần nhận trong response.
- **Resolver/DataFetcher thực thi** field bằng cách sử dụng arguments để tìm, lọc, tính toán hoặc thay đổi dữ liệu.

Argument không phải là một field con. Nó là đầu vào của field đang được gọi. Các field con có thể có arguments riêng theo định nghĩa trong schema.

## 2. Cú pháp khai báo field và arguments trong SDL

Một field có thể được khai báo theo dạng:

~~~graphql
fieldName(argumentName: ArgumentType): ReturnType
~~~

Một field có nhiều arguments:

~~~graphql
fieldName(
    firstArgument: FirstType
    secondArgument: SecondType
): ReturnType
~~~

Ví dụ:

~~~graphql
type Query {
    book(id: ID!): Book
    books(authorId: ID!, limit: Int = 20): [Book!]!
}
~~~

Field `book` có một argument bắt buộc là `id`. Field `books` có hai arguments:

- `authorId: ID!` là bắt buộc và không được null.
- `limit: Int = 20` có giá trị mặc định là 20; client có thể bỏ qua argument này.

Arguments được khai báo bên trong cặp ngoặc tròn sau tên field. Mỗi argument có tên, kiểu dữ liệu và có thể có giá trị mặc định.

### 2.1. Argument có tên, không phải tham số theo vị trí

GraphQL sử dụng arguments có tên. Client phải chỉ rõ tên argument khi truyền giá trị:

~~~graphql
query {
    books(authorId: "author-12", limit: 10) {
        id
        title
    }
}
~~~

Thứ tự truyền arguments không ảnh hưởng ý nghĩa của operation:

~~~graphql
query {
    books(limit: 10, authorId: "author-12") {
        id
        title
    }
}
~~~

Hai operation trên tương đương về arguments. GraphQL không gán giá trị dựa trên vị trí như lời gọi hàm có tham số positional.

Tên argument phải khớp với tên đã khai báo trong schema. Nếu truyền một argument không tồn tại, operation sẽ không vượt qua bước validation.

### 2.2. Field không có argument

Không phải field nào cũng cần argument:

~~~graphql
type Query {
    currentUser: User
    featuredBooks: [Book!]!
}
~~~

Client có thể gọi trực tiếp:

~~~graphql
query {
    currentUser {
        id
        displayName
    }
    featuredBooks {
        id
        title
    }
}
~~~

Chỉ thêm argument khi client thực sự cần cung cấp đầu vào để xác định kết quả hoặc hành vi của field.

### 2.3. Arguments cũng có thể xuất hiện trên nested field

Arguments không chỉ dành cho root field của `Query` hoặc `Mutation`. Một field trên object type cũng có thể nhận arguments:

~~~graphql
type Book {
    id: ID!
    title: String!
    reviews(first: Int = 10): [Review!]!
}
~~~

Client có thể yêu cầu số lượng review khác nhau cho từng cuốn sách:

~~~graphql
query {
    book(id: "book-42") {
        title
        reviews(first: 5) {
            id
            rating
            comment
        }
    }
}
~~~

Ở đây `first` là argument của field `reviews`, không phải của field `book`. Mỗi field có danh sách arguments riêng được schema định nghĩa.

## 3. Các kiểu dữ liệu có thể dùng cho argument

Argument sử dụng các kiểu input hợp lệ của GraphQL. Những kiểu phổ biến gồm scalar, enum, list và input object.

### 3.1. Scalar

Scalar phù hợp với đầu vào đơn giản:

~~~graphql
type Query {
    book(id: ID!): Book
    books(limit: Int, minRating: Float): [Book!]!
    searchBooks(keyword: String!, exactMatch: Boolean = false): [Book!]!
}
~~~

Các scalar dựng sẵn:

| Scalar | Ví dụ giá trị |
| --- | --- |
| `Int` | `10` |
| `Float` | `4.5` |
| `String` | `"Spring GraphQL"` |
| `Boolean` | `true` hoặc `false` |
| `ID` | `"book-42"` |

`ID` dùng cho định danh. Nó được truyền dưới dạng chuỗi hoặc số nguyên theo quy tắc coercion của GraphQL, nhưng trong response thường được serialize thành chuỗi. Dùng `ID` khi argument mang ý nghĩa định danh; dùng `String` cho văn bản thông thường.

### 3.2. Enum

Nếu argument chỉ nhận một tập lựa chọn hữu hạn, enum giúp schema thể hiện rõ các giá trị hợp lệ:

~~~graphql
enum BookStatus {
    DRAFT
    PUBLISHED
    ARCHIVED
}

type Query {
    booksByStatus(status: BookStatus!): [Book!]!
}
~~~

Client truyền enum value không có dấu ngoặc kép:

~~~graphql
query {
    booksByStatus(status: PUBLISHED) {
        id
        title
    }
}
~~~

Giá trị `PUBLISHED` là một enum literal, không phải chuỗi `"PUBLISHED"`. Nếu truyền chuỗi thay cho enum, operation có thể bị lỗi coercion do kiểu không tương thích.

### 3.3. List

Argument có thể nhận một danh sách:

~~~graphql
type Query {
    booksByIds(ids: [ID!]!): [Book!]!
}
~~~

Client truyền list literal:

~~~graphql
query {
    booksByIds(ids: ["book-1", "book-2", "book-3"]) {
        id
        title
    }
}
~~~

Khai báo `[ID!]!` có nghĩa:

- Giá trị argument là một danh sách và không được null.
- Mỗi phần tử trong danh sách phải là một ID không null.
- Danh sách rỗng vẫn là một giá trị hợp lệ, trừ khi nghiệp vụ có quy tắc kiểm tra riêng.

Cần phân biệt các dạng:

| Khai báo | Ý nghĩa |
| --- | --- |
| `[ID]` | Danh sách có thể null; phần tử có thể null |
| `[ID!]` | Danh sách có thể null; phần tử không được null |
| `[ID]!` | Danh sách không được null; phần tử có thể null |
| `[ID!]!` | Danh sách và mọi phần tử đều không được null |

### 3.4. Input object

Khi một field cần nhiều điều kiện liên quan, có thể gom chúng vào input object:

~~~graphql
input BookFilter {
    titleContains: String
    authorId: ID
    status: BookStatus
    minRating: Float
}

type Query {
    books(filter: BookFilter): [Book!]!
}
~~~

Client truyền object đầu vào:

~~~graphql
query {
    books(
        filter: {
            titleContains: "GraphQL"
            status: PUBLISHED
            minRating: 4.0
        }
    ) {
        id
        title
    }
}
~~~

Input object giúp lời gọi field gọn hơn khi có nhiều điều kiện. Nó cũng giúp schema thể hiện một nhóm dữ liệu đầu vào có ý nghĩa.

Input object chỉ được chứa các kiểu input hợp lệ như scalar, enum, input object khác và list của chúng. Không thể dùng trực tiếp output object type như `Book` hoặc `Author` làm kiểu của một input field.

## 4. Argument bắt buộc, nullable và giá trị mặc định

Thiết kế tính bắt buộc của argument là quyết định quan trọng. Nó ảnh hưởng cách client gọi API và cách resolver diễn giải dữ liệu đầu vào.

### 4.1. Argument non-null

Dấu `!` đánh dấu argument không được nhận null:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

Client phải cung cấp `id` và giá trị không được null:

~~~graphql
query {
    book(id: "book-42") {
        title
    }
}
~~~

Các trường hợp không hợp lệ:

~~~graphql
query {
    book {
        title
    }
}
~~~

~~~graphql
query {
    book(id: null) {
        title
    }
}
~~~

GraphQL validation/coercion sẽ phát hiện argument bắt buộc bị thiếu hoặc nhận null trước khi resolver field được thực thi.

### 4.2. Argument nullable

Nếu không có dấu `!`, argument có thể nhận null hoặc bị bỏ qua:

~~~graphql
type Query {
    books(status: BookStatus): [Book!]!
}
~~~

Client có thể gọi:

~~~graphql
query {
    books {
        id
        title
    }
}
~~~

Hoặc truyền null:

~~~graphql
query {
    books(status: null) {
        id
        title
    }
}
~~~

Ý nghĩa của việc bỏ qua hoặc truyền null phụ thuộc quy tắc nghiệp vụ mà resolver áp dụng. Ví dụ, một ứng dụng có thể hiểu bỏ qua status là lấy tất cả sách, còn status null cũng có nghĩa không lọc. Ứng dụng khác có thể định nghĩa hai trường hợp này khác nhau.

### 4.3. Giá trị mặc định

Argument có thể khai báo giá trị mặc định trong SDL:

~~~graphql
type Query {
    books(limit: Int = 20): [Book!]!
}
~~~

Nếu client không truyền `limit`, GraphQL sử dụng giá trị mặc định 20:

~~~graphql
query {
    books {
        id
        title
    }
}
~~~

Client vẫn có thể ghi đè:

~~~graphql
query {
    books(limit: 5) {
        id
        title
    }
}
~~~

Có thể khai báo argument non-null nhưng vẫn có default value:

~~~graphql
type Query {
    popularBooks(limit: Int! = 10): [Book!]!
}
~~~

Với khai báo này, client có thể bỏ qua argument vì schema có giá trị mặc định. Nếu client truyền tường minh null, request không hợp lệ vì kiểu argument là non-null.

### 4.4. Bỏ qua argument và truyền null là hai ý nghĩa khác nhau

Xét khai báo:

~~~graphql
type Query {
    books(status: BookStatus): [Book!]!
}
~~~

Hai lời gọi sau có thể được ứng dụng diễn giải khác nhau:

~~~graphql
query {
    books {
        id
    }
}
~~~

~~~graphql
query {
    books(status: null) {
        id
    }
}
~~~

Trường hợp đầu không cung cấp argument `status`. Trường hợp thứ hai cung cấp argument và giá trị là null.

Khác biệt này đặc biệt quan trọng với mutation update. Bỏ qua một field đầu vào thường có nghĩa "không thay đổi giá trị hiện tại", trong khi truyền null có thể có nghĩa "xóa giá trị hiện tại". Nếu resolver hoặc binder không giữ được thông tin về việc argument bị bỏ qua hay được truyền null, hãy dùng một kiểu biểu diễn có thể phân biệt hai trạng thái đó ở tầng ứng dụng.

## 5. Dùng variables để truyền arguments

Literal phù hợp với ví dụ ngắn, nhưng ứng dụng thực tế thường dùng variables để tách dữ liệu khỏi document.

Operation khai báo variable ở đầu:

~~~graphql
query FindBook($id: ID!, $includeReviews: Boolean! = false) {
    book(id: $id) {
        id
        title
        reviews(first: 5) @include(if: $includeReviews) {
            id
            rating
        }
    }
}
~~~

Client truyền variables dưới dạng JSON:

~~~json
{
    "id": "book-42",
    "includeReviews": true
}
~~~

`$id` được truyền vào argument `id` của field `book`. `$includeReviews` được dùng làm điều kiện cho directive `@include`.

Variables có kiểu và có thể có default value. Kiểu variable phải tương thích với kiểu argument nơi nó được sử dụng.

Ví dụ hợp lệ:

~~~graphql
query FindBook($id: ID!) {
    book(id: $id) {
        id
        title
    }
}
~~~

Ví dụ không tương thích:

~~~graphql
query FindBook($id: Int!) {
    book(id: $id) {
        id
        title
    }
}
~~~

Nếu argument `book.id` yêu cầu `ID!`, variable `Int!` không phải kiểu khai báo phù hợp chỉ vì giá trị thực tế có thể là một số. GraphQL kiểm tra tương thích kiểu dựa trên schema và định nghĩa variable.

### 5.1. Variables cho input object

Input object cũng có thể được truyền qua variable:

~~~graphql
query SearchBooks($filter: BookFilter, $limit: Int = 20) {
    books(filter: $filter, limit: $limit) {
        id
        title
    }
}
~~~

Variables:

~~~json
{
    "filter": {
        "titleContains": "Spring",
        "status": "PUBLISHED",
        "minRating": 4.0
    },
    "limit": 10
}
~~~

Trong JSON, enum value được biểu diễn bằng chuỗi vì JSON không có kiểu enum riêng. GraphQL runtime sẽ coercion chuỗi đó theo enum đã khai báo trong schema.

### 5.2. Vì sao nên ưu tiên variables?

Variables mang lại một số lợi ích:

- Tránh ghép dữ liệu người dùng trực tiếp vào chuỗi GraphQL.
- Giúp GraphQL runtime kiểm tra kiểu đầu vào.
- Tái sử dụng một operation với nhiều bộ dữ liệu.
- Dễ quản lý operation trong client và theo dõi request.
- Hỗ trợ cơ chế cache operation tốt hơn khi document không thay đổi.

Không nên tạo operation bằng cách nối chuỗi giá trị từ người dùng vào query. Hãy truyền dữ liệu qua variables để giữ document ổn định và giảm rủi ro lỗi cú pháp hoặc injection ở tầng xây dựng query.

## 6. Arguments trên nested field và phạm vi của chúng

Arguments thuộc về field cụ thể được khai báo trong schema. Chúng không tự động truyền xuống các field con.

Ví dụ schema:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    title: String!
    reviews(first: Int = 10): [Review!]!
}

type Review {
    id: ID!
    rating: Int!
    comment: String
}
~~~

Operation:

~~~graphql
query {
    book(id: "book-42") {
        title
        reviews(first: 3) {
            rating
            comment
        }
    }
}
~~~

`id` là argument của `Query.book`. `first` là argument của `Book.reviews`. Resolver của `reviews` nhận `first` theo định nghĩa field của nó.

Nếu client yêu cầu nhiều field lồng nhau, mỗi field có thể có arguments độc lập:

~~~graphql
query {
    book(id: "book-42") {
        title
        reviews(first: 3) {
            rating
        }
    }
    anotherBook: book(id: "book-99") {
        title
        reviews(first: 8) {
            rating
        }
    }
}
~~~

Hai lần gọi `book` có thể dùng các arguments khác nhau; mỗi lần gọi `reviews` cũng có thể nhận một giá trị `first` riêng. GraphQL xử lý mỗi field occurrence trong selection set theo arguments của nó.

Nếu muốn dùng cùng một giá trị cho nhiều field, có thể khai báo một variable rồi truyền vào từng vị trí tương ứng.

## 7. Arguments trong Spring for GraphQL

Trong Spring for GraphQL, các arguments của field được truyền vào controller method hoặc DataFetcher. Với annotated controller, `@Argument` giúp bind giá trị argument vào tham số Java.

Giả sử schema:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

Controller:

~~~java
@Controller
class BookController {

    private final BookService bookService;

    BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    Book book(@Argument("id") String bookId) {
        return bookService.findById(bookId);
    }
}
~~~

`@QueryMapping` ánh xạ method với field `book` trên root type `Query`. `@Argument("id")` lấy giá trị argument `id` và bind vào tham số Java `bookId`.

Tên tham số Java không nhất thiết phải trùng tên argument nếu bạn chỉ rõ tên trong annotation. Cách này giúp mapping rõ ràng và không phụ thuộc vào việc compiler có giữ metadata tên tham số hay không.

### 7.1. Dùng @Argument trên nested field

Ví dụ schema:

~~~graphql
type Book {
    id: ID!
    title: String!
    reviews(first: Int = 10): [Review!]!
}
~~~

Controller có thể ánh xạ field `reviews`:

~~~java
@Controller
class BookReviewController {

    private final ReviewService reviewService;

    BookReviewController(ReviewService reviewService) {
        this.reviewService = reviewService;
    }

    @SchemaMapping(typeName = "Book", field = "reviews")
    List<Review> reviews(
            Book book,
            @Argument("first") Integer first) {

        return reviewService.findByBookId(book.id(), first);
    }
}
~~~

`@SchemaMapping` chỉ rõ method xử lý field `reviews` của type `Book`. Tham số `Book book` là source object cha đang được resolve; `@Argument("first")` nhận argument của field.

Nếu tên method trùng tên field và source type có thể suy ra từ kiểu tham số, Spring có thể suy luận một phần mapping. Tuy nhiên, chỉ rõ `typeName` và `field` trong ví dụ giúp người đọc nhận biết rõ field đang được xử lý.

### 7.2. Dùng @Argument với input object

Schema:

~~~graphql
input BookFilter {
    titleContains: String
    authorId: ID
    status: BookStatus
}

type Query {
    books(filter: BookFilter): [Book!]!
}
~~~

Java record:

~~~java
public record BookFilter(
        String titleContains,
        String authorId,
        BookStatus status) {
}
~~~

Controller:

~~~java
@QueryMapping
List<Book> books(@Argument("filter") BookFilter filter) {
    return bookService.search(filter);
}
~~~

Spring for GraphQL dùng cơ chế argument binding để chuyển input map thành object Java tương ứng. Kiểu Java cần có constructor hoặc property binding phù hợp với cấu trúc input.

Với input object phức tạp, nên dùng DTO/record dành riêng cho GraphQL input. Điều đó giúp schema không bị phụ thuộc trực tiếp vào entity persistence và giúp validation đầu vào rõ ràng hơn.

### 7.3. Dùng tên argument tường minh

Có thể viết:

~~~java
@QueryMapping
Book book(@Argument("id") String bookId) {
    return bookService.findById(bookId);
}
~~~

Hoặc khi tên tham số Java được lưu và được Spring sử dụng để suy luận:

~~~java
@QueryMapping
Book book(@Argument String id) {
    return bookService.findById(id);
}
~~~

Trong code dùng cho tài liệu hoặc API quan trọng, chỉ rõ tên argument giúp mapping dễ đọc và tránh phụ thuộc cấu hình biên dịch.

### 7.4. Kiểu Java nên phản ánh nullability

Nếu argument có thể null, hãy dùng kiểu tham chiếu như `Integer`, `Boolean` hoặc `String` thay vì primitive tương ứng.

Ví dụ:

~~~graphql
type Query {
    books(limit: Int): [Book!]!
}
~~~

~~~java
@QueryMapping
List<Book> books(@Argument("limit") Integer limit) {
    int effectiveLimit = limit != null ? limit : 20;
    return bookService.findBooks(effectiveLimit);
}
~~~

Nếu dùng `int` cho argument nullable, Java không thể biểu diễn giá trị null. Với argument non-null, có thể dùng primitive khi phù hợp, nhưng kiểu tham chiếu vẫn hữu ích nếu muốn kiểm tra hoặc xử lý giá trị trước khi gọi service.

Khi schema đã định nghĩa default value, GraphQL runtime áp dụng default trước khi resolver sử dụng argument. Vì vậy, resolver nên có một quy tắc nhất quán và tránh vô tình áp dụng một default thứ hai khác với schema.

## 8. Phân biệt argument bị bỏ qua và argument null trong Java

Trong một số mutation cập nhật, hai trạng thái sau có ý nghĩa khác nhau:

- Client không gửi field đầu vào: giữ nguyên giá trị hiện tại.
- Client gửi field với giá trị null: xóa giá trị hiện tại nếu nghiệp vụ cho phép.

Ví dụ:

~~~graphql
input UpdateBookInput {
    id: ID!
    subtitle: String
}

type Mutation {
    updateBook(input: UpdateBookInput!): Book!
}
~~~

Hai variables sau không tương đương:

~~~json
{
    "input": {
        "id": "book-42"
    }
}
~~~

~~~json
{
    "input": {
        "id": "book-42",
        "subtitle": null
    }
}
~~~

Trong input đầu tiên, `subtitle` bị bỏ qua. Trong input thứ hai, `subtitle` được cung cấp với giá trị null.

Nếu chỉ bind cả hai trường hợp thành một biến Java `String subtitle`, giá trị nhận được có thể đều là null. Khi nghiệp vụ cần phân biệt chúng, Spring for GraphQL cung cấp kiểu `ArgumentValue<T>` để biểu diễn cả trạng thái bị bỏ qua và trạng thái có giá trị, bao gồm null.

Ví dụ minh họa:

~~~java
public record UpdateBookInput(
        String id,
        ArgumentValue<String> subtitle) {
}
~~~

Service có thể dựa vào trạng thái của `ArgumentValue` để quyết định có cập nhật field hay không. Cách sử dụng API cụ thể cần theo phiên bản Spring for GraphQL của dự án; hãy kiểm tra package và phương thức hiện hành khi triển khai.

Không phải mọi input đều cần phân biệt hai trạng thái. Chỉ dùng cơ chế này khi nghiệp vụ có ý nghĩa rõ ràng cho việc bỏ qua và xóa giá trị.

## 9. Thiết kế arguments cho filter, sort và pagination

Các Query trả về danh sách thường cần arguments để lọc, sắp xếp và phân trang. Nên thiết kế chúng có quy ước nhất quán.

### 9.1. Filter

Ví dụ:

~~~graphql
input BookFilter {
    titleContains: String
    authorId: ID
    status: BookStatus
}

type Query {
    books(filter: BookFilter): [Book!]!
}
~~~

Client có thể chỉ truyền một phần điều kiện:

~~~graphql
query {
    books(filter: { status: PUBLISHED }) {
        id
        title
    }
}
~~~

Resolver cần xác định rõ cách kết hợp nhiều điều kiện: AND, OR, tìm kiếm chính xác hay tìm kiếm một phần. Không nên để client phải đoán ý nghĩa của từng filter field.

### 9.2. Sort

Có thể dùng enum để giới hạn field và hướng sắp xếp:

~~~graphql
enum BookSortField {
    TITLE
    PUBLISHED_AT
}

enum SortDirection {
    ASC
    DESC
}

input BookSort {
    field: BookSortField!
    direction: SortDirection! = ASC
}

type Query {
    books(sort: BookSort): [Book!]!
}
~~~

Client:

~~~graphql
query {
    books(sort: { field: PUBLISHED_AT, direction: DESC }) {
        id
        title
    }
}
~~~

Enum giúp tránh việc client truyền tên cột database tùy ý. Server vẫn cần ánh xạ enum sang trường sort được phép trong ứng dụng.

### 9.3. Offset pagination

Một cách phân trang đơn giản:

~~~graphql
type Query {
    books(page: Int = 0, size: Int = 20): [Book!]!
}
~~~

Client:

~~~graphql
query {
    books(page: 2, size: 10) {
        id
        title
    }
}
~~~

Cần quy định rõ page bắt đầu từ 0 hay 1, size tối đa là bao nhiêu và cách xử lý giá trị âm. Không nên chỉ dựa vào client để bảo vệ tài nguyên server.

### 9.4. Cursor pagination

Với dữ liệu thay đổi thường xuyên hoặc danh sách lớn, cursor pagination có thể phù hợp hơn:

~~~graphql
type Query {
    books(first: Int = 20, after: String): BookConnection!
}

type BookConnection {
    edges: [BookEdge!]!
    pageInfo: PageInfo!
}

type BookEdge {
    cursor: String!
    node: Book!
}

type PageInfo {
    hasNextPage: Boolean!
    endCursor: String
}
~~~

Client truyền `first` và `after` để yêu cầu trang kế tiếp. Cursor nên được tạo từ một vị trí ổn định trong thứ tự dữ liệu; không nên để client tùy ý truyền một biểu thức SQL hoặc tên cột làm cursor.

Dù dùng offset hay cursor, hãy giữ tên arguments nhất quán giữa các field danh sách có cùng hành vi.

## 10. Validation và xử lý lỗi của arguments

GraphQL kiểm tra kiểu và cấu trúc argument trước khi gọi resolver. Một số lỗi phổ biến:

- Thiếu argument non-null.
- Truyền null cho argument non-null.
- Truyền literal không đúng kiểu.
- Variable không tương thích với kiểu argument.
- Truyền enum value không tồn tại.
- Input object chứa field không được khai báo trong schema.

Ví dụ schema:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

Operation thiếu argument bắt buộc:

~~~graphql
query {
    book {
        id
    }
}
~~~

Operation truyền sai kiểu:

~~~graphql
query {
    book(id: 123.45) {
        id
    }
}
~~~

GraphQL runtime phát hiện lỗi parse, validation hoặc coercion và không thực thi field như một request hợp lệ. Đây là lớp kiểm tra hợp đồng, nhưng chưa thay thế validation nghiệp vụ.

Ví dụ, argument `limit` có thể đúng kiểu `Int` nhưng vẫn không hợp lệ theo nghiệp vụ nếu client truyền số âm hoặc một giá trị quá lớn. Resolver hoặc service cần kiểm tra giới hạn đó:

~~~java
@QueryMapping
List<Book> books(@Argument("limit") Integer limit) {
    int effectiveLimit = limit == null ? 20 : limit;

    if (effectiveLimit < 1 || effectiveLimit > 100) {
        throw new IllegalArgumentException("limit must be between 1 and 100");
    }

    return bookService.findBooks(effectiveLimit);
}
~~~

Trong ứng dụng thật, nên chuyển lỗi nghiệp vụ sang GraphQL error có thông điệp phù hợp và không để lộ chi tiết nội bộ. Có thể dùng cơ chế xử lý exception của Spring for GraphQL như `@GraphQlExceptionHandler` hoặc `DataFetcherExceptionResolver`.

## 11. Bảo mật khi thiết kế arguments

Arguments là dữ liệu do client gửi. Không được xem một argument hợp lệ về kiểu là dữ liệu đáng tin cậy về quyền truy cập.

Ví dụ không nên thiết kế Query cho phép client truyền tùy ý tenant:

~~~graphql
type Query {
    books(tenantId: ID!): [Book!]!
}
~~~

Nếu người dùng có thể thay `tenantId`, họ có thể thử truy cập dữ liệu của tenant khác nếu server không kiểm tra quyền.

Trong hệ thống multi-tenant, tenant nên được xác định từ danh tính đã xác thực hoặc security context đáng tin cậy. Nếu schema cần nhận một tenant identifier cho nghiệp vụ đặc biệt, server vẫn phải xác minh người dùng có quyền truy cập tenant đó.

Một số nguyên tắc:

- Kiểm tra quyền truy cập đối tượng trong service hoặc resolver.
- Không dùng `userId`, `role` hoặc `tenantId` từ client làm bằng chứng xác thực.
- Giới hạn page size, số lượng ID trong list và độ phức tạp filter.
- Chỉ cho phép các trường sort đã định nghĩa; không ghép tên field từ input trực tiếp vào SQL.
- Dùng parameter binding trong repository/query thay vì nối chuỗi dữ liệu đầu vào.
- Không ghi toàn bộ arguments vào log nếu chúng có thể chứa dữ liệu nhạy cảm.

Argument là một phần của API contract; authorization và validation nghiệp vụ vẫn thuộc trách nhiệm server.

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `Unknown argument` | Tên argument không tồn tại trên field | Kiểm tra SDL và tên argument trong operation |
| Thiếu argument bắt buộc | Argument có dấu `!` nhưng client bỏ qua | Truyền giá trị hoặc thiết kế lại nullability nếu thực sự tùy chọn |
| `Expected type ...` | Literal hoặc variable sai kiểu | Đồng bộ kiểu với schema |
| Enum value không hợp lệ | Dùng giá trị không có trong enum hoặc truyền nhầm thành chuỗi literal | Dùng đúng enum value đã khai báo |
| Resolver nhận null | Argument bị bỏ qua, explicit null hoặc mapping không đúng | Kiểm tra schema, variables và kiểu Java |
| Không bind được input object | DTO không tương thích với cấu trúc input | Kiểm tra constructor, record và property binding |
| Cập nhật không phân biệt bỏ qua và null | Kiểu Java chỉ biểu diễn một giá trị null | Cân nhắc `ArgumentValue<T>` |
| Query trả quá nhiều dữ liệu | Thiếu giới hạn pagination hoặc filter | Đặt default, maximum và validation ở server |
| Người dùng truy cập dữ liệu ngoài phạm vi | Tin argument định danh do client gửi | Kiểm tra quyền tại server và security context |

## 13. Quy trình thiết kế một field có arguments

Khi bổ sung một field mới vào schema, có thể thực hiện theo trình tự:

1. **Xác định kết quả field.** Field trả về scalar, object hay danh sách?
2. **Xác định dữ liệu đầu vào.** Client cần cung cấp thông tin nào để chọn hoặc biến đổi kết quả?
3. **Chọn kiểu argument.** Dùng scalar, enum, list hay input object theo cấu trúc nghiệp vụ.
4. **Quyết định nullability.** Giá trị nào bắt buộc? Trường hợp nào được bỏ qua hoặc truyền null?
5. **Đặt default nếu có.** Giá trị mặc định phải có ý nghĩa ổn định và phù hợp nghiệp vụ.
6. **Viết operation mẫu.** Thử cả literal, variables, giá trị thiếu và null.
7. **Ánh xạ vào resolver.** Dùng `@Argument` và kiểu Java tương thích.
8. **Kiểm tra nghiệp vụ và quyền.** Xác thực giới hạn, quyền truy cập và tính nhất quán của dữ liệu.
9. **Kiểm thử lỗi đầu vào.** Bao gồm sai kiểu, thiếu argument, enum không hợp lệ và input object không hợp lệ.
10. **Theo dõi hiệu năng.** Đặc biệt với nested field và danh sách lớn.

## 14. Tổng kết

Field là đơn vị dữ liệu mà client yêu cầu trong GraphQL; argument là đầu vào có tên được truyền cho field đó. Schema định nghĩa tên, kiểu, nullability và default value của từng argument. Operation cung cấp literal hoặc variables để thực thi field. Arguments có thể dùng scalar, enum, list hoặc input object và xuất hiện trên cả root field lẫn nested field.

Trong Spring for GraphQL, `@Argument` bind giá trị đầu vào vào tham số Java của controller hoặc DataFetcher; `@SchemaMapping` giúp xử lý arguments trên nested field. Thiết kế tốt cần làm rõ trường hợp bắt buộc, nullable, default, bỏ qua và explicit null. Khi kết hợp validation, authorization và giới hạn tài nguyên ở server, arguments trở thành cách rõ ràng và an toàn để client điều khiển dữ liệu mà API cung cấp.

