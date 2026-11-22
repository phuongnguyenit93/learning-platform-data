# Type extension

GraphQL SDL cho phép mở rộng một type đã được khai báo bằng cú pháp `extend`. Type extension giúp chia schema thành nhiều file hoặc nhiều phần theo domain mà vẫn tạo thành **một GraphQL schema thống nhất** khi ứng dụng khởi động. Ví dụ, module sách có thể khai báo `Query` và `Book` cơ bản; module tìm kiếm bổ sung field `booksByAuthor` vào `Query` bằng `extend type Query`.

Type extension là một phần của ngôn ngữ định nghĩa schema GraphQL. Nó thay đổi định nghĩa schema được xây dựng từ SDL, không phải thao tác thay đổi Java class, không tự tạo resolver và cũng không phải cơ chế cập nhật schema động khi ứng dụng đang chạy. Với Spring for GraphQL, các file SDL được tìm theo cấu hình schema locations, sau đó được kết hợp để tạo schema mà GraphQL Java thực thi.

## 1. Vì sao cần type extension?

Trong một schema nhỏ, có thể đặt toàn bộ type vào một file. Khi API phát triển, một file duy nhất dễ trở nên dài và khó phân chia quyền sở hữu. Chia SDL theo domain giúp nhóm phát triển quản lý từng phần độc lập:

```text
src/main/resources/graphql/
├── common/
│   └── scalars.graphqls
├── catalog/
│   ├── catalog.graphqls
│   └── catalog-search.graphqls
└── account/
    ├── account.graphqls
    └── account-profile.graphqls
```

File `catalog.graphqls` có thể định nghĩa type gốc:

```graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
```

File `catalog-search.graphqls` bổ sung field liên quan đến tìm kiếm:

```graphql
extend type Query {
    booksByAuthor(authorId: ID!): [Book!]!
}
```

Sau khi các file được kết hợp, `Query` có cả `book` và `booksByAuthor`. Client chỉ nhìn thấy một type `Query`; nó không cần biết field được khai báo trong file nào.

Nếu viết thêm một định nghĩa `type Query` khác với cùng tên như một type mới, schema có thể gặp lỗi định nghĩa trùng lặp. Khi mục đích là bổ sung field vào type hiện có, phải dùng `extend type Query`.

## 2. Cú pháp và nguyên tắc chung

Cú pháp tổng quát của một type extension có dạng:

```graphql
extend type TypeName {
    newField: ReturnType
}
```

Từ khóa `extend` cho parser biết đây là phần bổ sung cho một định nghĩa đã có. Tên và loại type phải khớp với type gốc. Ví dụ, `extend type Book` chỉ có thể mở rộng một object type tên `Book`, không thể mở rộng một enum hoặc input object cùng tên.

Các nguyên tắc quan trọng:

- Type được mở rộng phải tồn tại trong schema tổng hợp và phải đúng loại type.
- Phần mở rộng chỉ bổ sung thành phần mới, không khai báo lại field, enum value hoặc union member đã có.
- Các type được tham chiếu trong field mới cũng phải tồn tại trong schema tổng hợp sau khi kết hợp các file.
- Sau khi ghép các định nghĩa và extension, toàn bộ schema vẫn phải vượt qua quy tắc validation của GraphQL.
- Có thể có nhiều extension cho cùng một type, miễn là các phần bổ sung không xung đột và schema cuối cùng hợp lệ.

Type extension không phải cách ghi đè một field. Nếu cần đổi kiểu trả về hoặc thay đổi argument của field đã tồn tại, hãy chỉnh sửa định nghĩa gốc và đánh giá ảnh hưởng tương thích API.

## 3. Mở rộng object type

`extend type` thường được dùng để bổ sung field vào object type. Có thể thêm field đơn giản, field có argument, field trả về list hoặc field tham chiếu type khác:

```graphql
type Book {
    id: ID!
    title: String!
}

type Author {
    id: ID!
    name: String!
}

extend type Book {
    author: Author
    relatedBooks(limit: Int = 5): [Book!]!
}
```

Sau khi mở rộng, `Book` có các field `id`, `title`, `author` và `relatedBooks`. `author` có thể trả về `null`; `relatedBooks` phải trả về một list không null và không có phần tử null.

Object type extension cũng có thể bổ sung interface mà object type triển khai:

```graphql
scalar DateTime

interface Node {
    id: ID!
}

type Book {
    id: ID!
    title: String!
}
```

Trong ví dụ, `Book` đã có field `id` tương thích với interface `Node`, nên có thể khai báo thêm quan hệ triển khai interface. Nếu interface có field mà object chưa cung cấp đúng kiểu và quy tắc argument, schema validation sẽ thất bại. Một extension có thể bổ sung cả interface và field mới trong cùng block:

```graphql
extend type Book implements Node {
    publishedAt: DateTime
}
```

## 4. Mở rộng interface

Interface mô tả một tập field mà các object type triển khai phải cung cấp. Có thể bổ sung field vào interface bằng `extend interface`:

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

extend interface Node {
    createdAt: DateTime!
}
```

Khi thêm `createdAt` vào `Node`, mọi object type triển khai `Node` trong schema cuối cùng cũng phải có field tương thích `createdAt`. Vì vậy, extension của interface có phạm vi ảnh hưởng rộng hơn việc chỉ thêm một field vào một object type. Cần cập nhật hoặc kiểm tra tất cả các implementation liên quan trước khi schema có thể được xây dựng thành công.

Ví dụ các object type được cập nhật để đáp ứng interface mới:

```graphql
extend type Book {
    createdAt: DateTime!
}

extend type Author {
    createdAt: DateTime!
}
```

Nếu không thể bảo đảm mọi implementation cung cấp field mới, cân nhắc thêm field vào từng object type riêng thay vì mở rộng interface dùng chung. Quyết định này phụ thuộc vào contract mà các client cần dựa vào.

## 5. Mở rộng union

Union biểu diễn một kết quả có thể thuộc nhiều object type khác nhau. `extend union` cho phép thêm một object type vào tập thành viên:

```graphql
type Book {
    id: ID!
    title: String!
}

type Author {
    id: ID!
    name: String!
}

union SearchResult = Book | Author

type Magazine {
    id: ID!
    issue: Int!
}

extend union SearchResult = Magazine

type Query {
    search(keyword: String!): [SearchResult!]!
}
```

Sau khi mở rộng, `SearchResult` có thể chứa `Book`, `Author` hoặc `Magazine`. Client cần dùng inline fragment để lấy field đặc thù của từng object type:

```graphql
query {
    search(keyword: "GraphQL") {
        ... on Book {
            title
        }
        ... on Author {
            name
        }
        ... on Magazine {
            issue
        }
    }
}
```

Các member của union phải là object type. Không thể thêm scalar, enum hoặc interface trực tiếp làm member của union. Việc thêm member mới có thể ảnh hưởng client dùng code generation hoặc xử lý kết quả theo kiểu exhaustive; client nên có nhánh xử lý cho loại kết quả chưa biết.

## 6. Mở rộng enum

Enum giới hạn một giá trị vào tập tên đã khai báo. `extend enum` thêm giá trị mới vào tập đó:

```graphql
enum BookStatus {
    DRAFT
    PUBLISHED
}

extend enum BookStatus {
    ARCHIVED
    OUT_OF_PRINT
}
```

Schema cuối cùng cho phép `BookStatus` nhận bốn giá trị. Các enum value mới không được trùng với giá trị đã khai báo trong enum gốc hoặc extension khác.

Thêm enum value thường là thay đổi mang tính mở rộng ở phía schema, nhưng client có thể cần cập nhật code. Một số client sinh enum thành kiểu đóng và dùng `switch` có thể chưa xử lý giá trị mới. Khi phát triển API công khai, nên xem xét cách client xử lý giá trị enum chưa nhận diện.

## 7. Mở rộng input object

`extend input` thêm field vào input object đã tồn tại:

```graphql
enum BookStatus {
    DRAFT
    PUBLISHED
}

input BookFilter {
    keyword: String
    status: BookStatus
}

extend input BookFilter {
    authorId: ID
    publishedAfter: DateTime
}
```

Client có thể truyền các field mới trong input object:

```graphql
query {
    books(filter: {
        status: PUBLISHED
        authorId: "author-01"
    }) {
        id
        title
    }
}
```

Khi mở rộng input object đang được client sử dụng, đặc biệt chú ý đến field mới có kiểu non-null. Nếu thêm một field bắt buộc mà không có default value, các client cũ không gửi field đó có thể trở thành request không hợp lệ. Để thay đổi tương thích hơn, thường nên thêm field nullable hoặc cung cấp default value phù hợp với nghiệp vụ.

## 8. Mở rộng scalar

Scalar mô tả một giá trị đơn như chuỗi, số hoặc kiểu miền nghiệp vụ. `extend scalar` có thể bổ sung directive cho scalar đã được khai báo:

```graphql
scalar DateTime

extend scalar DateTime @specifiedBy(
    url: "https://scalars.graphql.org/andimarek/date-time"
)
```

Extension này bổ sung metadata về định dạng được scalar sử dụng. Nó không thay đổi cách Java parse input hoặc serialize output. Với custom scalar như `DateTime`, ứng dụng vẫn cần cấu hình `Coercing` phù hợp trong runtime wiring của GraphQL Java hoặc cơ chế cấu hình tương ứng của Spring for GraphQL.

Scalar extension không phải cơ chế để thêm field vào scalar hoặc thay đổi kiểu dữ liệu bên trong scalar. Nếu muốn thay đổi hành vi serialize/coercion, phải cập nhật phần triển khai scalar ở runtime và kiểm thử tương thích.

## 9. Schema extension và type extension

`extend schema` có cú pháp riêng để bổ sung operation type hoặc directive áp dụng cho schema. Nó khác với `extend type`, vốn mở rộng một object type cụ thể.

Ví dụ schema gốc khai báo query root:

```graphql
schema {
    query: Query
}

type Book {
    id: ID!
}

type Query {
    book(id: ID!): Book
}

type Mutation {
    renameBook(id: ID!, title: String!): Book!
}
```

Một file khác có thể bổ sung mutation root vào schema đã khai báo:

```graphql
extend schema {
    mutation: Mutation
}
```

Sau khi hợp nhất, schema có cả query root và mutation root. Operation root được cấu hình ở cấp schema, trong khi các field như `renameBook` được định nghĩa bên trong object type `Mutation`. Không nhầm `extend schema` với `extend type Mutation`: cái thứ nhất thêm operation type vào schema, cái thứ hai thêm field vào object type `Mutation`.

## 10. Kết hợp nhiều file SDL trong Spring for GraphQL

Spring Boot có thể tìm các file schema trong classpath, thường từ `src/main/resources/graphql/`. Ví dụ cấu hình:

```yaml
spring:
  graphql:
    schema:
      locations: classpath:graphql/**/
```

Giả sử các file được tổ chức như sau:

```text
src/main/resources/graphql/
├── core/
│   └── schema.graphqls
└── catalog/
    ├── catalog.graphqls
    └── search.graphqls
```

`schema.graphqls` có thể định nghĩa `Query` và các type dùng chung. `catalog.graphqls` định nghĩa `Book`, còn `search.graphqls` dùng `extend type Query` để bổ sung field tìm kiếm. Spring for GraphQL nạp các resource theo locations đã cấu hình, kết hợp type definitions và extensions, rồi tạo `GraphQlSource` chứa schema hoàn chỉnh cho GraphQL Java.

Điều quan trọng là tất cả file được nạp phải tạo thành một schema hợp lệ. Đường dẫn resource tìm được file không đảm bảo nội dung SDL hợp lệ; type gốc vẫn phải tồn tại, không được trùng field và các quan hệ interface/union phải thỏa quy tắc type system.

## 11. Type extension không tự tạo resolver

SDL extension chỉ bổ sung contract. Nếu mở rộng `Query` bằng field `booksByAuthor`, ứng dụng vẫn cần cung cấp cách lấy dữ liệu cho field đó. Với Spring for GraphQL, có thể khai báo controller:

```java
@Controller
public class BookSearchController {

    private final BookService bookService;

    public BookSearchController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> booksByAuthor(@Argument String authorId) {
        return bookService.findByAuthorId(authorId);
    }
}
```

Field mới trong `Book` cũng cần resolver nếu không thể lấy từ source object bằng property fetcher mặc định:

```java
@Controller
public class BookAuthorController {

    private final AuthorService authorService;

    public BookAuthorController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }
}
```

Spring phát hiện các phương thức mapping trong controller bean và kết nối chúng với field trong schema runtime. Nếu SDL có field nhưng thiếu resolver và source object cũng không có property tương ứng, query có thể trả về `null` hoặc dữ liệu không như mong muốn tùy kiểu field và cơ chế fetch mặc định.

## 12. Quy tắc validation và lỗi thường gặp

GraphQL kiểm tra schema sau khi kết hợp định nghĩa gốc và extension. Một số lỗi thường gặp:

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `Cannot extend type ... because it is not defined` | Type gốc chưa được nạp hoặc sai tên | Kiểm tra file định nghĩa type và schema locations |
| Mở rộng sai loại type | Dùng `extend type` cho enum/interface/input hoặc ngược lại | Dùng đúng từ khóa extension tương ứng |
| Field bị định nghĩa trùng | Extension khai báo lại field đã có | Xóa field trùng hoặc sửa định nghĩa gốc |
| Enum value bị trùng | Nhiều file thêm cùng một giá trị | Chỉ khai báo mỗi enum value một lần |
| Union member bị trùng hoặc không phải object | Member đã tồn tại hoặc tham chiếu sai loại type | Kiểm tra danh sách union members |
| Interface có field mới nhưng object chưa triển khai | Các implementation không còn thỏa interface contract | Cập nhật các object type liên quan hoặc thiết kế lại interface |
| Input object có field bắt buộc mới | Client cũ không gửi field mới | Cân nhắc nullable hoặc default value |
| Schema hợp lệ nhưng field không lấy được dữ liệu | Chưa có resolver phù hợp | Bổ sung `@QueryMapping`, `@SchemaMapping` hoặc mapping tương ứng |

Lỗi parse/validation của SDL thường khiến ứng dụng không thể tạo schema trong lúc khởi động. Khi đó, hãy kiểm tra tên type gốc, đúng loại extension, field/member trùng và quan hệ giữa interface với object implementation. Nếu schema đã khởi động nhưng field trả dữ liệu sai, hãy kiểm tra resolver và nguồn dữ liệu thay vì sửa cú pháp extension.

## 13. Thiết kế extension an toàn khi schema phát triển

Chia file theo domain và để một nơi sở hữu định nghĩa gốc của mỗi type. Các domain khác chỉ bổ sung field bằng extension, tránh nhiều nhóm cùng chỉnh sửa hoặc khai báo lại field gốc. Dùng tên field nhất quán và kiểm tra toàn bộ schema sau khi thêm extension.

Đánh giá ảnh hưởng của từng loại thay đổi:

- Thêm field nullable vào object type thường là cách mở rộng ít ảnh hưởng đến client hiện có.
- Thêm field vào interface tác động đến mọi object type triển khai interface đó.
- Thêm enum value hoặc union member có thể yêu cầu client xử lý thêm trường hợp mới.
- Thêm input field non-null không có default có thể làm operation của client cũ không còn hợp lệ.
- Thay đổi kiểu trả về, argument hoặc nullability của field hiện có có thể phá vỡ contract đã công bố.

Type extension giúp tổ chức schema theo module và domain, nhưng không làm mất các quy tắc nhất quán của GraphQL type system. Mọi file cuối cùng vẫn phải ghép thành một schema hợp lệ, mọi field được công bố cần có cách phân giải dữ liệu phù hợp, và mọi thay đổi contract cần được đánh giá cùng các client đang sử dụng API.
