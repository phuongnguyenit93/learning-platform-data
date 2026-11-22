# Schema Definition Language (SDL) trong GraphQL

GraphQL Schema Definition Language (SDL) là ngôn ngữ khai báo dùng để mô tả hợp đồng của một GraphQL API. SDL cho biết API có những kiểu dữ liệu nào, mỗi kiểu có field gì, field nhận argument nào, kiểu trả về ra sao và client được phép thực hiện những operation nào. Schema là căn cứ để GraphQL kiểm tra query trước khi thực thi và tạo cấu trúc response nhất quán.

Trong Spring for GraphQL, schema thường được viết thành các file `.graphqls` hoặc `.gqls` trong tài nguyên của ứng dụng. Spring for GraphQL kết hợp các định nghĩa này thành schema GraphQL Java; các resolver được khai báo bằng `@QueryMapping`, `@SchemaMapping` và annotation liên quan sẽ cung cấp dữ liệu cho những field tương ứng.

Sau bài này, bạn có thể:

- Đọc và viết cú pháp SDL cho schema, type, field, argument và directive.
- Phân biệt scalar, object, enum, input object, interface và union.
- Hiểu ý nghĩa của list và nullability trong kiểu dữ liệu GraphQL.
- Thiết kế root operation type và tổ chức schema thành nhiều file.
- Dùng mô tả, custom scalar, directive và type extension đúng mục đích.
- Đánh giá ảnh hưởng của thay đổi schema đối với client và resolver Spring.

## 1. SDL mô tả hợp đồng GraphQL

REST API thường được mô tả bằng các endpoint và cấu trúc request/response. GraphQL tập trung vào một schema có kiểu dữ liệu rõ ràng. Client gửi một operation chọn các field cần đọc; schema xác định field đó có tồn tại hay không, argument có hợp lệ không và kiểu dữ liệu nào được trả về.

Ví dụ, một API thư viện có thể khai báo:

```graphql
type Query {
    book(id: ID!): Book
    books(limit: Int = 20): [Book!]!
}

type Book {
    id: ID!
    title: String!
    publishedYear: Int
}
```

Schema trên định nghĩa hai field đọc dữ liệu ở root type `Query`. `book` nhận `id` bắt buộc và trả về một `Book` có thể null. `books` nhận `limit` tùy chọn, mặc định là 20, và trả về một danh sách không null gồm các phần tử `Book` không null.

SDL không chứa cách truy vấn database hoặc quy tắc nghiệp vụ. Nó mô tả hình dạng và ràng buộc của API; resolver thực hiện việc lấy hoặc biến đổi dữ liệu. Vì vậy, một schema có thể được kiểm tra và tài liệu hóa ngay cả khi phần resolver chưa được triển khai đầy đủ.

## 2. Cấu trúc cơ bản của một schema

Một schema GraphQL gồm các định nghĩa kiểu và có một hoặc nhiều root operation type. Ba operation type tiêu chuẩn là:

- `Query`: đọc dữ liệu.
- `Mutation`: thay đổi dữ liệu.
- `Subscription`: nhận luồng sự kiện.

Ví dụ schema đầy đủ:

```graphql
schema {
    query: Query
    mutation: Mutation
    subscription: Subscription
}

type Query {
    book(id: ID!): Book
    books: [Book!]!
}

type Mutation {
    createBook(input: CreateBookInput!): Book!
}

type Subscription {
    bookCreated: Book!
}
```

`schema` chỉ rõ object type nào là root cho từng operation. Nếu dùng đúng tên mặc định `Query`, `Mutation` và `Subscription`, định nghĩa `schema` có thể được lược bỏ; GraphQL mặc định nhận diện các root type theo những tên đó. Nếu đặt tên khác, chẳng hạn `RootQuery`, cần khai báo `schema { query: RootQuery }` để chỉ rõ root query type. Root query type là bắt buộc; mutation và subscription là tùy chọn.

Tên type và field phân biệt chữ hoa/chữ thường. Theo quy ước phổ biến, tên object type, interface, enum, input và scalar dùng PascalCase; field, argument và enum value dùng camelCase hoặc UPPER_SNAKE_CASE tùy quy ước dự án. Quan trọng nhất là chọn một quy ước nhất quán.

## 3. Khai báo field và argument

Một object type chứa các field mà client có thể chọn. Mỗi field có tên, có thể có danh sách argument và phải có kiểu trả về:

```graphql
type Query {
    book(id: ID!): Book
    searchBooks(text: String!, limit: Int = 10): [Book!]!
}
```

Trong ví dụ:

- `book` là tên field.
- `id` là argument có kiểu `ID!`, nên client phải truyền giá trị.
- `Book` là kiểu trả về; vì không có `!`, field có thể trả `null`.
- `searchBooks` nhận `text` bắt buộc và `limit` tùy chọn với giá trị mặc định là 10.
- `[Book!]!` biểu thị field luôn trả về một danh sách và từng phần tử trong danh sách cũng không được null.

Argument có thể là scalar, enum hoặc input object. Không thể dùng một object output type thông thường làm kiểu argument. Khi một thao tác cần nhiều giá trị đầu vào có cấu trúc, nên gom chúng vào input object thay vì tạo quá nhiều argument rời rạc.

```graphql
input BookFilter {
    authorId: ID
    publishedAfter: Int
    tags: [String!]
}

type Query {
    books(filter: BookFilter, limit: Int = 20): [Book!]!
}
```

Default value được viết trực tiếp trong SDL. String đặt trong dấu nháy kép, số viết như literal, enum value không đặt trong dấu nháy và list/object dùng cú pháp tương ứng. Default value chỉ được dùng khi client không cung cấp argument hoặc input field đó; nó không thay thế một giá trị null mà client chủ động truyền vào.

## 4. Scalar type

Scalar là kiểu dữ liệu đơn giản, không có field con. GraphQL định nghĩa sẵn năm scalar cơ bản:

| Scalar | Ý nghĩa |
| --- | --- |
| `Int` | Số nguyên có dấu 32-bit |
| `Float` | Số thực dấu phẩy động độ chính xác kép |
| `String` | Chuỗi ký tự |
| `Boolean` | Giá trị `true` hoặc `false` |
| `ID` | Định danh, được serialize thành chuỗi; thường dùng cho khóa nhận diện object |

Ví dụ:

```graphql
type Book {
    id: ID!
    title: String!
    pageCount: Int
    rating: Float
    available: Boolean!
}
```

Không nên dùng `Int` cho mọi giá trị số. Nếu dữ liệu có thể vượt phạm vi số nguyên 32-bit, hãy cân nhắc custom scalar phù hợp hoặc biểu diễn bằng chuỗi theo hợp đồng API. `ID` diễn tả định danh, không phải cam kết rằng giá trị đó là số nguyên.

### Custom scalar

Khi API cần kiểu dữ liệu như ngày giờ, tiền tệ hoặc số thập phân có độ chính xác cao, có thể khai báo scalar riêng:

```graphql
scalar DateTime
scalar Decimal

type AuditEvent {
    occurredAt: DateTime!
    amount: Decimal
}
```

SDL chỉ đặt tên scalar và đưa nó vào type system. Ứng dụng vẫn phải định nghĩa cách parse giá trị đầu vào, validate, serialize giá trị đầu ra và ánh xạ nó với kiểu Java. Với GraphQL Java, phần này thường được triển khai bằng `GraphQLScalarType`/`Coercing` rồi đăng ký qua `RuntimeWiringConfigurer`; dự án cũng có thể dùng scalar đã được cung cấp bởi thư viện mở rộng.

Nếu scalar có một chuẩn định dạng rõ ràng, directive `@specifiedBy` có thể gắn URL mô tả hợp đồng serialization:

```graphql
scalar DateTime @specifiedBy(url: "https://example.org/specs/date-time")
```

URL trong ví dụ cần được thay bằng tài liệu đặc tả thực tế mà API cam kết tuân theo. Hãy quy định rõ timezone, độ chính xác, định dạng đầu vào và cách biểu diễn giá trị null để client không phải đoán.

## 5. Object type và quan hệ giữa các kiểu

Object type là thành phần trung tâm của schema. Nó mô tả một đối tượng mà client có thể truy vấn field:

```graphql
type Author {
    id: ID!
    name: String!
}

type Book {
    id: ID!
    title: String!
    author: Author
}
```

Field `Book.author` tham chiếu đến object type `Author`, tạo quan hệ lồng nhau. Client có thể chọn field con theo nhu cầu:

```graphql
query {
    book(id: "book-42") {
        title
        author {
            name
        }
    }
}
```

Schema cho phép mô tả quan hệ sâu hơn, nhưng không quyết định quan hệ đó được tải bằng join, truy vấn riêng, cache hay DataLoader. Những lựa chọn này thuộc tầng thực thi. Khi thiết kế nhiều field quan hệ, cần tính đến N+1 và giới hạn độ sâu/trọng số query ở phía server.

## 6. List và nullability

GraphQL dùng dấu ngoặc vuông để khai báo danh sách và dấu `!` để đánh dấu một kiểu không được null. Hai ký hiệu có thể kết hợp, tạo ra bốn dạng quan trọng:

| Kiểu | Field có thể null? | Danh sách có thể null? | Phần tử có thể null? |
| --- | --- | --- | --- |
| `[Book]` | Có | Có | Có |
| `[Book!]` | Có | Có | Không |
| `[Book]!` | Không | Không | Có |
| `[Book!]!` | Không | Không | Không |

Ví dụ:

```graphql
type Query {
    optionalBooks: [Book]
    booksWithRequiredItems: [Book!]!
}
```

`[Book!]!` yêu cầu resolver trả về một danh sách khác null và không có phần tử null. Nếu resolver không thể tìm thấy dữ liệu, nó cần trả danh sách rỗng thay vì null. Nếu một phần tử bắt buộc bị null hoặc phát sinh lỗi khi phân giải, GraphQL áp dụng quy tắc null propagation: giá trị null lan lên field cha gần nhất cho phép null, đồng thời response có thể chứa lỗi.

Hãy chọn nullability theo hợp đồng nghiệp vụ:

- Dùng non-null khi ứng dụng có thể bảo đảm field luôn có giá trị hợp lệ.
- Dùng nullable khi không có dữ liệu là kết quả bình thường, chẳng hạn tìm sách theo ID không tồn tại.
- Không đánh dấu mọi field là non-null chỉ để response trông chặt chẽ; lỗi thực thi có thể làm null lan rộng hơn dự kiến.
- Với list, quyết định riêng việc danh sách có thể null và từng phần tử có thể null.

Thay đổi nullability là thay đổi hợp đồng. Đổi output từ nullable sang non-null có thể khiến response lỗi nếu dữ liệu cũ hoặc một resolver vẫn trả null. Đổi input từ nullable sang non-null có thể khiến các client cũ không còn gửi được request hợp lệ.

## 7. Enum type

Enum giới hạn một field vào tập giá trị được schema công bố:

```graphql
enum BookStatus {
    DRAFT
    PUBLISHED
    ARCHIVED
}

type Book {
    id: ID!
    status: BookStatus!
}
```

Client chỉ được gửi một enum value hợp lệ trong operation. Enum giúp schema tự mô tả tốt hơn so với dùng chuỗi tự do, đồng thời hỗ trợ công cụ sinh code tạo kiểu enum ở phía client.

Khi thêm enum value mới, một số client có switch exhaustive hoặc giả định chỉ có tập giá trị cũ có thể cần cập nhật. Vì vậy, thêm enum value thường ít rủi ro hơn xóa hoặc đổi tên nhưng vẫn cần xem xét cách client xử lý giá trị chưa biết.

## 8. Input object và output object

Input object dùng cho dữ liệu client gửi vào. Object type dùng cho dữ liệu server trả về. Hai nhóm có mục đích khác nhau và không thể thay thế tùy ý cho nhau.

```graphql
input CreateBookInput {
    title: String!
    authorId: ID!
    publishedYear: Int
}

type Book {
    id: ID!
    title: String!
    publishedYear: Int
    author: Author
}

type Mutation {
    createBook(input: CreateBookInput!): Book!
}
```

Input object chỉ chứa input field; mỗi field của nó có kiểu scalar, enum hoặc input object, có thể được bọc trong list/non-null. Input field không có argument và không thể tham chiếu trực tiếp đến object type, interface hoặc union. Ngược lại, output field có thể trả về object và có thể nhận argument.

Trong Java, input object có thể được bind vào record hoặc DTO:

```java
public record CreateBookInput(
        String title,
        String authorId,
        Integer publishedYear) {}

@MutationMapping
public Book createBook(@Argument("input") CreateBookInput input) {
    return bookService.create(input);
}
```

SDL xác định cấu trúc và nullability; validation nghiệp vụ như tiêu đề không được để trống, tác giả phải tồn tại hoặc năm xuất bản nằm trong khoảng hợp lệ cần được thực hiện ở tầng ứng dụng. Có thể kết hợp Bean Validation trong DTO/service nếu dự án đã cấu hình hỗ trợ.

## 9. Interface và union

Interface mô tả một tập field chung mà nhiều object type phải triển khai. Nó hữu ích khi các object khác nhau có cùng một phần cấu trúc:

```graphql
interface Node {
    id: ID!
}

type Book implements Node {
    id: ID!
    title: String!
}

type Author implements Node {
    id: ID!
    name: String!
}

type Query {
    node(id: ID!): Node
}
```

Object triển khai interface phải cung cấp các field được yêu cầu với kiểu tương thích. Client có thể truy vấn field chung trên interface; nếu cần field riêng của từng object, dùng inline fragment:

```graphql
query {
    node(id: "42") {
        id
        ... on Book {
            title
        }
        ... on Author {
            name
        }
    }
}
```

Union biểu diễn kết quả có thể là một trong nhiều object type mà không yêu cầu chúng có chung field:

```graphql
union SearchResult = Book | Author

type Query {
    search(text: String!): [SearchResult!]!
}
```

Union chỉ gồm object type. Client phải dùng inline fragment để chọn field cụ thể của từng kiểu thành viên; không thể truy vấn một field tùy ý trực tiếp trên union ngoài meta field `__typename`.

Chọn interface khi các kiểu chia sẻ một hợp đồng field thực sự. Chọn union khi các kiểu chỉ cần xuất hiện trong cùng một vị trí kết quả nhưng không có cấu trúc chung đáng kể.

## 10. Directive trong SDL

Directive là chỉ thị có tên, có thể nhận argument và được gắn vào những vị trí được định nghĩa. GraphQL có một số directive chuẩn cho type system, trong đó hai directive thường gặp là:

- `@deprecated`: đánh dấu field hoặc enum value không còn được khuyến nghị sử dụng; có thể cung cấp lý do.
- `@specifiedBy`: gắn URL mô tả hợp đồng của custom scalar.

Ví dụ đánh dấu field cũ:

```graphql
type Book {
    id: ID!
    title: String!
    authorName: String @deprecated(reason: "Use author { name } instead.")
    author: Author
}
```

Có thể định nghĩa directive riêng trong SDL:

```graphql
enum Role {
    USER
    EDITOR
    ADMIN
}

directive @requiresRole(role: Role!) on FIELD_DEFINITION

type Query {
    publicBooks: [Book!]!
    moderationQueue: [Book!]! @requiresRole(role: ADMIN)
}
```

Phần `on FIELD_DEFINITION` giới hạn vị trí directive có thể xuất hiện. GraphQL quy định tập vị trí hợp lệ như `OBJECT`, `FIELD_DEFINITION`, `ARGUMENT_DEFINITION`, `INPUT_FIELD_DEFINITION`, `SCALAR`, `ENUM_VALUE` và các vị trí dành cho executable document như `FIELD`, `QUERY` hoặc `FRAGMENT_SPREAD`.

Chỉ khai báo directive trong SDL không tự thực thi phân quyền hay thay đổi hành vi resolver. Ứng dụng phải có cơ chế đọc và áp dụng directive, ví dụ qua schema wiring, instrumentation hoặc lớp bảo mật thích hợp. Với Spring Security, kiểm tra quyền ở service/resolver vẫn là một phần quan trọng; directive không nên chỉ được xem như một nhãn trang trí tạo cảm giác đã bảo vệ field.

## 11. Mô tả schema và comment

SDL hỗ trợ description bằng chuỗi đặt trước định nghĩa hoặc field. Description được giữ trong schema và có thể xuất hiện trong introspection, tài liệu hoặc công cụ khám phá API:

```graphql
"""Một cuốn sách có thể được tìm kiếm trong thư viện."""
type Book {
    """Định danh ổn định của cuốn sách."""
    id: ID!

    """Tiêu đề hiển thị cho người đọc."""
    title: String!
}
```

Comment bắt đầu bằng `#` hữu ích cho ghi chú trong file nguồn nhưng không tương đương description của schema. Nếu nội dung giải thích là một phần tài liệu API dành cho người dùng schema, hãy dùng description thay vì chỉ ghi comment.

Description nên nói rõ ý nghĩa nghiệp vụ, đơn vị đo, quy tắc null hoặc giới hạn quan trọng. Tránh chép lại tên field theo cách không cung cấp thêm thông tin.

## 12. Mở rộng type và chia schema thành nhiều file

Khi schema lớn dần, có thể chia định nghĩa theo miền nghiệp vụ hoặc nhóm type. GraphQL SDL hỗ trợ `extend` để bổ sung field vào một type đã được định nghĩa:

```graphql
# books.graphqls
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
```

```graphql
# authors.graphqls
type Author {
    id: ID!
    name: String!
}

extend type Query {
    author(id: ID!): Author
}

extend type Book {
    author: Author
}
```

`extend type` bổ sung field hoặc interface vào một type đã tồn tại trong schema tổng hợp. Type được mở rộng phải có định nghĩa gốc và extension phải đóng góp nội dung hợp lệ; không dùng extension rỗng. Các định nghĩa trùng tên không hợp lệ nếu tạo ra xung đột trong schema.

Trong ứng dụng Spring Boot dùng Spring for GraphQL, schema resource mặc định thường được tìm trong `classpath:graphql/**/` với file `.graphqls` hoặc `.gqls`. Có thể tổ chức theo domain, ví dụ:

```text
src/main/resources/
└── graphql/
    ├── common.graphqls
    ├── books/
    │   ├── book-types.graphqls
    │   └── book-queries.graphqls
    └── authors/
        ├── author-types.graphqls
        └── author-queries.graphqls
```

Các file được kết hợp thành một schema; việc tách file chỉ giúp tổ chức mã nguồn, không tạo ra nhiều schema độc lập cho từng folder. Vì vậy, tên type, field và extension phải nhất quán trên toàn bộ tập tài nguyên. Nếu dự án thay đổi vị trí schema, cấu hình schema locations phải trỏ đúng các tài nguyên cần nạp.

## 13. Từ SDL đến resolver trong Spring for GraphQL

SDL khai báo field và kiểu trả về. Resolver cung cấp giá trị khi GraphQL thực thi field. Ví dụ schema:

```graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
```

Có thể triển khai resolver cho root field bằng Spring controller:

```java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id).orElse(null);
    }
}
```

`@QueryMapping` liên kết method với `Query.book`; `@Argument("id")` bind argument được khai báo trong SDL. Nếu tên field, argument hoặc kiểu dữ liệu giữa schema và resolver không tương thích, schema wiring hoặc quá trình thực thi có thể thất bại. Các field đơn giản như `Book.id` và `Book.title` có thể được GraphQL Java đọc từ getter/record accessor mà không cần resolver riêng.

Schema cũng không thay thế validation đầu vào, authorization hoặc giới hạn tài nguyên. SDL có thể mô tả argument bắt buộc và kiểu dữ liệu, nhưng các quy tắc như người dùng có quyền đọc một cuốn sách hay query được phép sâu đến đâu cần được áp dụng ở server.

## 14. Kiểm tra tính hợp lệ của schema

Trước khi chạy ứng dụng, cần bảo đảm schema có thể parse và build thành một type system hợp lệ. Những lỗi thường gặp gồm:

- Không có root `Query` hoặc khai báo root type sai tên.
- Tham chiếu đến một type chưa được định nghĩa.
- Định nghĩa trùng tên type, field hoặc enum value.
- Dùng output object type ở vị trí input hoặc ngược lại.
- Object khai báo `implements` nhưng thiếu field bắt buộc hoặc có kiểu không tương thích.
- Union chứa kiểu không phải object type.
- Directive được dùng ở vị trí không nằm trong danh sách `on`.
- Argument hoặc default value không phù hợp với kiểu được khai báo.

Trong Spring for GraphQL, việc khởi tạo schema sẽ phát hiện nhiều lỗi cấu trúc và wiring sớm khi ứng dụng khởi động. Nên có kiểm thử khởi tạo schema và integration test gửi operation thực tế để phát hiện cả lỗi kết nối giữa SDL với resolver.

Ví dụ operation cần được schema chấp nhận:

```graphql
query FindBook($id: ID!) {
    book(id: $id) {
        id
        title
    }
}
```

Nếu schema không khai báo `book`, thiếu argument `id` hoặc kiểu argument không tương thích, GraphQL có thể từ chối operation ở bước validation trước khi gọi resolver. Đây là lợi ích quan trọng của schema có kiểu: nhiều lỗi hợp đồng được phát hiện trước khi truy cập dữ liệu.

## 15. Thiết kế schema có khả năng tiến hóa

Schema là hợp đồng công khai giữa server và client. Thay đổi schema cần được đánh giá theo khả năng tương thích:

| Thay đổi | Tác động thường gặp |
| --- | --- |
| Thêm field nullable mới vào object | Thường tương thích với client hiện tại |
| Thêm argument tùy chọn có default | Thường không buộc client cũ phải sửa request |
| Thêm argument bắt buộc không có default | Có thể làm operation cũ không hợp lệ |
| Xóa hoặc đổi tên field/argument | Breaking change với client đang sử dụng |
| Đổi output nullable thành non-null | Có thể gây lỗi nếu resolver vẫn có khả năng trả null |
| Đổi input nullable thành non-null | Client cũ có thể không còn gửi request hợp lệ |
| Thêm enum value | Có thể ảnh hưởng client xử lý enum exhaustive |
| Xóa enum value | Breaking change nếu client còn gửi hoặc xử lý value đó |

Khi cần thay field, có thể thêm field mới, đánh dấu field cũ bằng `@deprecated`, cập nhật client rồi mới xóa ở một phiên bản thay đổi hợp đồng phù hợp. Ví dụ:

```graphql
type Book {
    id: ID!
    authorName: String @deprecated(reason: "Use author { name } instead.")
    author: Author
}
```

Không nên đổi kiểu trả về hoặc input chỉ để làm schema ngắn hơn mà chưa kiểm tra dữ liệu hiện có và client tiêu thụ API. Các công cụ kiểm tra schema diff và kiểm thử contract có thể giúp phát hiện thay đổi nguy hiểm trong quy trình CI.

## 16. Quy trình viết SDL cho một tính năng mới

Khi thiết kế một tính năng GraphQL, có thể đi theo trình tự sau:

1. Xác định các operation client cần: đọc, thay đổi hay đăng ký sự kiện.
2. Xác định object type và mối quan hệ dữ liệu cần công bố.
3. Chọn scalar, enum, input object, interface hoặc union theo đúng vai trò của dữ liệu.
4. Khai báo field, argument, default value, list và nullability theo hợp đồng nghiệp vụ.
5. Viết description cho type và field quan trọng; dùng directive khi có ngữ nghĩa rõ ràng.
6. Chia file theo domain và dùng `extend` khi bổ sung vào root type hoặc type đã có.
7. Kiểm tra schema build thành công, sau đó nối resolver và viết operation test.
8. Đánh giá tương thích trước khi thay đổi schema đã được client sử dụng.

SDL là nền tảng của GraphQL API: nó làm rõ dữ liệu nào được công bố, cách client truy vấn và những ràng buộc mà server phải tuân thủ. Một schema tốt có type rõ ràng, nullability có chủ đích, input/output tách biệt và có thể tiến hóa mà không gây bất ngờ cho client. Trong Spring for GraphQL, giữ SDL nhất quán với resolver và kiểm thử schema trong quá trình phát triển giúp hợp đồng API dễ hiểu, dễ bảo trì và đáng tin cậy.
