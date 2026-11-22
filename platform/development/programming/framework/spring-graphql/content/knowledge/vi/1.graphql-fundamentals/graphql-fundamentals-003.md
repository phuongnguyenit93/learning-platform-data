# Schema và operation trong GraphQL

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích schema GraphQL mô tả những gì và operation dùng schema như thế nào.
- Đọc và viết schema bằng GraphQL Schema Definition Language (SDL).
- Khai báo object type, scalar, enum, input type, root operation type, danh sách và trường không null.
- Viết Query, Mutation và Subscription với arguments, variables, aliases, fragments và directives.
- Đọc cấu trúc request/response, nhận biết lỗi validation và lỗi trong quá trình thực thi.
- Biết cách đặt schema và kết nối các operation với handler trong ứng dụng Spring for GraphQL.

## 1. Schema và operation tạo thành hợp đồng API

GraphQL API có hai phần bổ sung cho nhau:

- **Schema** mô tả những kiểu dữ liệu, trường và operation mà server công bố. Đây là hợp đồng mà client có thể khám phá và kiểm tra.
- **Operation** là yêu cầu cụ thể mà client gửi lên, cho biết muốn đọc dữ liệu, thay đổi dữ liệu hay nhận luồng sự kiện nào, cùng với những trường cần lấy.

Ví dụ, schema có thể công bố trường **book(id: ID!): Book** trên root type **Query**. Client có thể gửi một query lấy **id**, **title** và **author.name** của một cuốn sách. Client không cần nhận toàn bộ thuộc tính của **Book**; nó chọn đúng các trường cần dùng.

Luồng xử lý tổng quát:

1. Client gửi một operation cùng variables (nếu có).
2. GraphQL server phân tích cú pháp và kiểm tra operation dựa trên schema.
3. Nếu operation hợp lệ, server thực thi các trường được yêu cầu và gọi phần xử lý dữ liệu tương ứng.
4. Server trả về dữ liệu theo cấu trúc selection set của client, kèm thông tin lỗi nếu có.

Schema là hợp đồng của API, không phải bản mô tả database. Một field có thể được tính toán, tổng hợp từ nhiều nguồn hoặc lấy từ service khác; schema chỉ quy định hình dạng và kiểu dữ liệu mà client được phép yêu cầu.

## 2. Khai báo schema bằng SDL

SDL là cú pháp khai báo kiểu của GraphQL. Một schema thường được chia thành các định nghĩa type. Mỗi type có tên và các field; mỗi field có kiểu trả về và có thể có arguments.

Ví dụ đơn giản:

~~~graphql
type Book {
    id: ID!
    title: String!
    publishedYear: Int
}
~~~

**Book** là một object type. Client có thể yêu cầu các field **id**, **title** và **publishedYear** khi truy vấn một giá trị thuộc kiểu **Book**.

### 2.1. Các scalar dựng sẵn

GraphQL có năm scalar dựng sẵn:

| Scalar | Ý nghĩa |
| --- | --- |
| **Int** | Số nguyên có dấu 32-bit |
| **Float** | Số thực |
| **String** | Chuỗi ký tự |
| **Boolean** | Giá trị đúng hoặc sai |
| **ID** | Định danh của một đối tượng |

**ID** thường được dùng cho khóa định danh và được serialize thành chuỗi trong response. Nó không bắt buộc phải là khóa chính của database; server có thể dùng UUID, mã nghiệp vụ hoặc một định danh khác.

Khi cần kiểu dữ liệu miền riêng như **DateTime**, schema có thể khai báo custom scalar:

~~~graphql
scalar DateTime

type Event {
    id: ID!
    startsAt: DateTime!
}
~~~

Khai báo **scalar DateTime** mới chỉ tạo tên kiểu trong schema. Ứng dụng vẫn phải cung cấp cách parse input và serialize output cho scalar đó trong runtime. Vì vậy, chỉ nên tạo custom scalar khi có quy ước biểu diễn và chuyển đổi rõ ràng.

### 2.2. Object type và quan hệ giữa các type

Object type mô tả một đối tượng có thể được client chọn field. Field có thể trả về scalar, enum, một object type khác hoặc danh sách các giá trị.

~~~graphql
type Author {
    id: ID!
    name: String!
    books: [Book!]!
}

type Book {
    id: ID!
    title: String!
    author: Author!
}
~~~

**Book.author** trả về một **Author**, còn **Author.books** trả về danh sách **Book**. Hai type có thể tham chiếu lẫn nhau; GraphQL cho phép mô tả quan hệ như vậy mà không cần nhúng toàn bộ dữ liệu vào schema.

Việc khai báo quan hệ không đồng nghĩa server tự động biết cách tải dữ liệu. Khi thực thi, server phải có cách lấy giá trị cho từng field, chẳng hạn từ thuộc tính của object, repository hoặc service.

### 2.3. Enum giới hạn tập giá trị

Dùng enum khi một field chỉ nhận một tập giá trị hữu hạn đã biết:

~~~graphql
enum BookStatus {
    DRAFT
    PUBLISHED
    ARCHIVED
}

type Book {
    id: ID!
    title: String!
    status: BookStatus!
}
~~~

Enum giúp client biết trước các giá trị hợp lệ và tránh phải đoán chuỗi tùy ý. Tên enum thường viết hoa theo quy ước phổ biến.

### 2.4. Danh sách và tính nullable

GraphQL dùng dấu ngoặc vuông để khai báo danh sách và dấu **!** để đánh dấu giá trị không được null. Hai quy tắc này có thể kết hợp:

| Khai báo | Ý nghĩa |
| --- | --- |
| **Book** | Một **Book** hoặc **null** |
| **Book!** | Bắt buộc có một **Book** |
| **[Book]** | Danh sách có thể là **null**; từng phần tử cũng có thể là **null** |
| **[Book!]** | Danh sách có thể là **null**; từng phần tử không được **null** |
| **[Book]!** | Danh sách không được **null**; từng phần tử có thể là **null** |
| **[Book!]!** | Danh sách và mọi phần tử đều không được **null** |

Ví dụ:

~~~graphql
type Query {
    book(id: ID!): Book
    books: [Book!]!
}
~~~

**book** có thể trả về **null**, phù hợp với trường hợp không tìm thấy sách. **books** phải trả về một danh sách; danh sách có thể rỗng nhưng không được là **null**, và không phần tử nào được là **null**.

Chọn nullable là một quyết định về hợp đồng API. Nếu dữ liệu thực tế có thể vắng mặt, đừng đánh dấu **!** chỉ để schema trông chặt chẽ hơn. Khi một field được khai báo non-null nhưng lúc thực thi lại trả về **null**, GraphQL tạo lỗi và đẩy giá trị **null** lên field cha gần nhất có thể nhận **null**. Điều này có thể làm một phần lớn hơn của response trở thành **null**.

### 2.5. Input type dành cho dữ liệu client gửi vào

Object type mô tả dữ liệu trả về. Với dữ liệu đầu vào, GraphQL dùng **input**:

~~~graphql
input CreateBookInput {
    title: String!
    authorId: ID!
    publishedYear: Int
}
~~~

Input object có thể chứa scalar, enum và input object khác, cùng các danh sách của những kiểu hợp lệ đó. Nó không thể dùng trực tiếp một output object type như **Book** hoặc **Author**.

Một mutation có thể nhận input object làm một argument:

~~~graphql
type Mutation {
    createBook(input: CreateBookInput!): Book!
}
~~~

Cách này giúp gom các thuộc tính liên quan vào một cấu trúc rõ ràng. Khi nghiệp vụ thêm trường đầu vào, schema có thể mở rộng input object mà không phải biến mutation thành một danh sách arguments dài.

## 3. Root operation types

GraphQL định nghĩa ba loại operation. Mỗi loại bắt đầu từ một root type tương ứng.

### 3.1. Query — đọc dữ liệu

**Query** là root type bắt buộc của một schema. Các field trên **Query** là điểm bắt đầu cho những yêu cầu đọc dữ liệu.

~~~graphql
type Query {
    book(id: ID!): Book
    books(limit: Int = 20): [Book!]!
}
~~~

Trong ví dụ này:

- **book** nhận argument bắt buộc **id**, trả về một **Book** hoặc **null**.
- **books** nhận **limit**, có giá trị mặc định là **20**, và trả về danh sách không null.

Query nên được thiết kế để đọc dữ liệu và không tạo side effect nghiệp vụ. GraphQL không tự ngăn một resolver Query ghi database; đây là quy ước mà API cần tuân thủ để client có thể dự đoán hành vi.

### 3.2. Mutation — thay đổi dữ liệu

**Mutation** là root type dành cho các thao tác tạo, cập nhật hoặc xóa dữ liệu.

~~~graphql
type Mutation {
    createBook(input: CreateBookInput!): Book!
}
~~~

Một mutation thường nhận input mô tả thay đổi và trả về dữ liệu cần thiết sau thay đổi. Trả về object thay vì chỉ trả về Boolean giúp client có thể chọn ngay những field cần cập nhật giao diện.

Các field cấp cao nhất trong một mutation operation được thực thi tuần tự theo thứ tự xuất hiện. Vì vậy, nếu một operation chứa nhiều mutation field phụ thuộc nhau, thứ tự thực thi có ý nghĩa. Tuy nhiên, mỗi mutation vẫn nên thể hiện một hành động nghiệp vụ rõ ràng; không nên gom nhiều thay đổi không liên quan vào cùng một request.

### 3.3. Subscription — nhận sự kiện theo thời gian

**Subscription** dùng để mô tả một luồng sự kiện mà client đăng ký nhận.

~~~graphql
type Subscription {
    bookAdded: Book!
}
~~~

Ví dụ này công bố field **bookAdded**. Khi có sự kiện sách mới, server có thể phát một kết quả cho client đang theo dõi. Subscription phù hợp với thông báo trạng thái, cập nhật trực tiếp hoặc sự kiện nghiệp vụ cần đẩy đến client.

Subscription có vòng đời dạng stream, khác với request/response thông thường của Query và Mutation. Server cần cấu hình transport hỗ trợ streaming, chẳng hạn WebSocket hoặc RSocket tùy kiến trúc ứng dụng. Một subscription operation chỉ chọn một root field để xác định luồng sự kiện cần theo dõi.

### 3.4. Khai báo schema root

Một schema hoàn chỉnh cho ví dụ sách có thể viết như sau:

~~~graphql
type Author {
    id: ID!
    name: String!
    books: [Book!]!
}

enum BookStatus {
    DRAFT
    PUBLISHED
    ARCHIVED
}

type Book {
    id: ID!
    title: String!
    status: BookStatus!
    publishedYear: Int
    author: Author!
}

input CreateBookInput {
    title: String!
    authorId: ID!
    publishedYear: Int
}

type Query {
    book(id: ID!): Book
    books(limit: Int = 20): [Book!]!
}

type Mutation {
    createBook(input: CreateBookInput!): Book!
}

type Subscription {
    bookAdded: Book!
}

schema {
    query: Query
    mutation: Mutation
    subscription: Subscription
}
~~~

Trong SDL, khai báo **schema** có thể được lược bỏ khi dùng tên root theo quy ước **Query**, **Mutation** và **Subscription**. Viết tường minh như trên có ích khi muốn thể hiện rõ entry point hoặc khi schema dùng tên root khác.

Không phải ứng dụng nào cũng cần cả ba root type. Query là bắt buộc; Mutation và Subscription chỉ cần khai báo khi API có các khả năng tương ứng.

## 4. Viết operation từ schema

Một operation là tài liệu thực thi (executable document) gồm operation definition và có thể có fragment. Client chỉ được chọn field có trong schema, truyền arguments đúng kiểu và chọn các field con cần thiết.

### 4.1. Selection set

Một query cơ bản:

~~~graphql
query {
    book(id: "book-101") {
        id
        title
        author {
            id
            name
        }
    }
}
~~~

Phần nằm trong dấu ngoặc nhọn sau **book** là selection set. Client chọn field **id**, **title** và **author**; vì **author** là object type, client tiếp tục chọn **id** và **name** bên trong.

Quy tắc quan trọng:

- Với field trả về scalar hoặc enum, không viết selection set con.
- Với field trả về object hoặc danh sách object, phải chọn các field con.
- Field được yêu cầu phải tồn tại trên type tương ứng trong schema.
- Client có thể chọn ít hoặc nhiều field tùy nhu cầu; server trả về đúng cấu trúc đã chọn.

Ví dụ sau không hợp lệ vì **title** là scalar:

~~~graphql
query {
    book(id: "book-101") {
        title {
            length
        }
    }
}
~~~

Tương tự, chỉ yêu cầu **book** mà không có selection set cũng không hợp lệ vì **book** trả về object **Book**.

### 4.2. Đặt tên operation

Nên đặt tên cho operation để dễ đọc log, theo dõi lỗi và kiểm soát request:

~~~graphql
query GetBookDetail {
    book(id: "book-101") {
        id
        title
    }
}
~~~

Tên operation là tùy chọn khi tài liệu chỉ có một operation. Nếu tài liệu chứa nhiều operation, request phải chỉ rõ operation nào sẽ chạy thông qua **operationName**.

~~~graphql
query GetBook($id: ID!) {
    book(id: $id) {
        id
        title
    }
}

query GetBooks($limit: Int) {
    books(limit: $limit) {
        id
        title
    }
}
~~~

Khi gửi tài liệu trên, client cần truyền **operationName** là **GetBook** hoặc **GetBooks** để server chọn đúng operation.

### 4.3. Arguments và variables

Arguments là giá trị truyền vào field. Có thể viết trực tiếp giá trị literal trong operation, nhưng với dữ liệu thay đổi theo từng request, nên dùng variables.

~~~graphql
query GetBook($id: ID!, $withAuthor: Boolean! = true) {
    book(id: $id) {
        id
        title
        author @include(if: $withAuthor) {
            id
            name
        }
    }
}
~~~

Variables được khai báo ở đầu operation. **$id: ID!** có nghĩa client phải cung cấp một giá trị ID không null. **$withAuthor** có giá trị mặc định là **true**, nên client có thể bỏ qua biến này nếu muốn dùng mặc định.

Phần variables được gửi riêng, thường dưới dạng JSON:

~~~json
{
    "id": "book-101",
    "withAuthor": true
}
~~~

Tách variables khỏi câu query có các lợi ích:

- Tránh nối chuỗi dữ liệu đầu vào vào nội dung GraphQL.
- Giúp server kiểm tra kiểu dữ liệu theo schema.
- Dễ tái sử dụng cùng một operation cho nhiều bộ dữ liệu.
- Giúp logging và cache operation ổn định hơn.

Khi dùng HTTP, request body thường có các thuộc tính **query**, **operationName** và **variables**:

~~~json
{
    "query": "query GetBook($id: ID!) { book(id: $id) { id title } }",
    "operationName": "GetBook",
    "variables": {
        "id": "book-101"
    }
}
~~~

Cách đóng gói request cụ thể còn phụ thuộc HTTP endpoint và transport mà ứng dụng cấu hình.

### 4.4. Mutation operation

Với schema ở trên, client có thể tạo sách như sau:

~~~graphql
mutation CreateBook($input: CreateBookInput!) {
    createBook(input: $input) {
        id
        title
        status
        author {
            id
            name
        }
    }
}
~~~

Variables:

~~~json
{
    "input": {
        "title": "GraphQL thực hành",
        "authorId": "author-12",
        "publishedYear": 2026
    }
}
~~~

Tên **CreateBookInput** trong khai báo variable phải khớp với kiểu input được schema công bố. Các field bắt buộc như **title** và **authorId** phải có mặt và không được null. **publishedYear** có thể bỏ qua vì schema không đánh dấu non-null.

Mutation chỉ có thể gọi được khi field **createBook** đã được khai báo trên root type **Mutation** và server có phần xử lý field đó. Việc field xuất hiện trong SDL chưa tự tạo ra logic lưu sách.

### 4.5. Subscription operation

Client đăng ký nhận sự kiện bằng operation:

~~~graphql
subscription OnBookAdded {
    bookAdded {
        id
        title
        author {
            name
        }
    }
}
~~~

Client giữ subscription mở theo transport đã cấu hình. Mỗi khi server phát một sự kiện hợp lệ, client nhận một kết quả có cấu trúc theo selection set trên. Client cần xử lý cả việc kết nối bị đóng, lỗi trong stream và hủy đăng ký khi không còn cần nhận sự kiện.

## 5. Các thành phần giúp tái sử dụng operation

### 5.1. Alias

Alias đặt tên khác cho field trong response. Nó hữu ích khi cần gọi cùng một field nhiều lần với arguments khác nhau:

~~~graphql
query CompareBookLists {
    newest: books(limit: 5) {
        id
        title
    }
    moreBooks: books(limit: 20) {
        id
        title
    }
}
~~~

Response sẽ có hai khóa **newest** và **moreBooks**. Alias chỉ đổi tên khóa trong kết quả, không thay đổi tên field trong schema.

### 5.2. Fragment

Fragment gom một selection set để tái sử dụng:

~~~graphql
fragment BookSummary on Book {
    id
    title
    status
}

query GetBookSummaries {
    books(limit: 10) {
        ...BookSummary
    }
}
~~~

**on Book** xác định type mà fragment áp dụng. Fragment giúp tránh lặp lại danh sách field khi nhiều operation hoặc nhiều vị trí cần cùng một cấu trúc dữ liệu.

Union nhóm nhiều object type mà một field có thể trả về; interface mô tả một tập field chung mà nhiều object type triển khai. Khi truy vấn union hoặc interface, inline fragment cho phép chọn field theo type cụ thể. Với ví dụ dưới đây, schema mở rộng thêm union và field tìm kiếm trên Query:

~~~graphql
union SearchResult = Book | Author

extend type Query {
    searchCatalog: [SearchResult!]!
}
~~~

Operation có thể chọn field phù hợp theo từng kiểu kết quả:

~~~graphql
query SearchCatalog {
    searchCatalog {
        __typename
        ... on Book {
            id
            title
        }
        ... on Author {
            id
            name
        }
    }
}
~~~

Trong ví dụ, **searchCatalog** có thể trả về nhiều kiểu. **__typename** cho biết kiểu cụ thể của mỗi kết quả; inline fragment chỉ yêu cầu field hợp lệ trên type tương ứng.

### 5.3. Directives

Directive thay đổi cách một phần operation được xử lý. Hai directive phổ biến là **@include** và **@skip**:

~~~graphql
query GetBook($id: ID!, $showStatus: Boolean!) {
    book(id: $id) {
        id
        title
        status @include(if: $showStatus)
        author {
            name
        }
    }
}
~~~

- **@include(if: true)** giữ field trong kết quả; **false** bỏ qua field.
- **@skip(if: true)** bỏ qua field; **false** giữ field.

GraphQL cũng có directive ở cấp schema, chẳng hạn **@deprecated**, để đánh dấu field hoặc enum value cũ:

~~~graphql
type Book {
    id: ID!
    title: String!
    oldTitle: String @deprecated(reason: "Use title instead")
}
~~~

Đánh dấu deprecated giúp client có thời gian chuyển sang field mới trước khi server loại bỏ field cũ.

## 6. Response và cách GraphQL báo lỗi

Một response thành công thường có thuộc tính **data**:

~~~json
{
    "data": {
        "book": {
            "id": "book-101",
            "title": "GraphQL thực hành"
        }
    }
}
~~~

Cấu trúc dữ liệu trong **data** phản ánh selection set của operation. Nếu client chỉ yêu cầu **id** và **title**, response không cần trả về những field khác của **Book**.

GraphQL phân biệt lỗi validation với lỗi trong lúc thực thi:

- **Lỗi parse hoặc validation** xảy ra khi tài liệu sai cú pháp hoặc operation không phù hợp schema, ví dụ field không tồn tại, truyền sai kiểu argument hoặc thiếu selection set. Server không thực thi operation không hợp lệ.
- **Lỗi execution** xảy ra khi một field đang được thực thi gặp vấn đề, ví dụ không tìm thấy dữ liệu hoặc service phía sau phát sinh lỗi. Response có thể chứa cả **data** và **errors**.

Ví dụ một field không lấy được dữ liệu:

~~~json
{
    "data": {
        "book": null
    },
    "errors": [
        {
            "message": "Book not found",
            "path": ["book"]
        }
    ]
}
~~~

Đây là ví dụ minh họa cấu trúc response; message thực tế phụ thuộc cách ứng dụng xử lý và chuyển đổi exception. Khi đọc lỗi, cần xem cả **message**, **path** và **data** để xác định field nào gặp vấn đề và phần dữ liệu nào vẫn dùng được.

Nullability ảnh hưởng trực tiếp đến phạm vi dữ liệu bị null khi có lỗi. Nếu một field non-null không thể tạo giá trị, GraphQL truyền null lên field cha gần nhất được phép null và ghi nhận lỗi. Vì vậy, khai báo **!** cần phản ánh cam kết thực tế của server.

## 7. Đưa schema và operation vào Spring for GraphQL

Trong ứng dụng Spring Boot dùng Spring for GraphQL, schema SDL thường được đặt trong thư mục tài nguyên:

~~~text
src/
└── main/
    └── resources/
        └── graphql/
            ├── schema.graphqls
            └── catalog.graphqls
~~~

Các file schema có thể được Spring Boot phát hiện và ghép thành schema ứng dụng theo cấu hình schema location. Chia schema thành nhiều file giúp tổ chức theo miền nghiệp vụ, nhưng các type và field sau khi ghép vẫn phải tạo thành một schema GraphQL hợp lệ.

Spring for GraphQL kết nối field trong schema với method xử lý thông qua annotation. Ví dụ:

~~~java
@Controller
class BookController {

    private final BookService bookService;

    BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    Book book(@Argument String id) {
        return bookService.findById(id);
    }

    @MutationMapping
    Book createBook(@Argument CreateBookInput input) {
        return bookService.create(input);
    }
}
~~~

Trong ví dụ:

- **@QueryMapping** ánh xạ method vào field **book** trên root type **Query**.
- **@MutationMapping** ánh xạ method vào field **createBook** trên root type **Mutation**.
- **@Argument** lấy giá trị argument từ operation và chuyển thành kiểu Java tương ứng.

Tên method thường được dùng để suy ra tên field. Có thể chỉ rõ tên field trong annotation khi cần. **CreateBookInput** là lớp hoặc record Java có cấu trúc tương thích với input object trong SDL.

Khi client yêu cầu field lồng nhau như **Book.author**, GraphQL cần biết cách lấy giá trị của field đó. Spring for GraphQL có thể dùng property access mặc định hoặc method được ánh xạ bằng **@SchemaMapping**. Chi tiết về resolver cho nested field, xử lý quan hệ và tối ưu việc tải dữ liệu được trình bày ở các bài chuyên sâu tiếp theo.

Đối với Subscription, method được ánh xạ bằng **@SubscriptionMapping** và phải cung cấp nguồn phát kết quả dạng stream phù hợp với mô hình ứng dụng. Ngoài resolver, server cần cấu hình transport hỗ trợ subscription để client có thể nhận nhiều kết quả trong cùng một lần đăng ký.

Có thể kiểm tra một operation bằng **GraphQlTester** trong test:

~~~java
graphQlTester.document("""
    query GetBook($id: ID!) {
        book(id: $id) {
            id
            title
        }
    }
    """)
    .variable("id", "book-101")
    .execute()
    .path("book.title")
    .entity(String.class)
    .isEqualTo("GraphQL thực hành");
~~~

Test này gửi một operation có variable, thực thi qua GraphQL runtime và kiểm tra một field trong response. Nó giúp xác minh đồng thời schema, operation và đường xử lý của field ở mức tích hợp.

## 8. Quy trình thiết kế và kiểm tra

Khi xây dựng một chức năng GraphQL, có thể đi theo trình tự sau:

1. **Xác định nhu cầu client.** Client cần đọc hoặc thay đổi dữ liệu gì? Những field nào thực sự cần xuất hiện trong response?
2. **Thiết kế output type.** Mô tả các object và quan hệ mà client được phép truy vấn. Dùng scalar và enum có ý nghĩa rõ ràng.
3. **Thiết kế root field.** Đặt thao tác đọc trên **Query**, thay đổi dữ liệu trên **Mutation**, và luồng sự kiện trên **Subscription**.
4. **Thiết kế arguments và input.** Đánh dấu field bắt buộc một cách có chủ đích; gom dữ liệu mutation vào input object khi phù hợp.
5. **Viết operation mẫu.** Dùng variables cho dữ liệu thay đổi, đặt tên operation và chỉ chọn field cần thiết.
6. **Kết nối handler trong Spring.** Đảm bảo mỗi field được công bố có cách lấy hoặc tạo giá trị phù hợp.
7. **Kiểm tra response và lỗi.** Thử dữ liệu tồn tại, không tồn tại, input sai, field nullable và trường hợp service gặp lỗi.

Một số nguyên tắc giúp schema dễ sử dụng và tiến hóa:

- Dùng tên type và field theo ngôn ngữ nghiệp vụ; tên field nên mô tả dữ liệu hoặc hành động cụ thể.
- Không công bố trực tiếp cấu trúc database nếu nó không phải hợp đồng phù hợp cho client.
- Chỉ đánh dấu non-null khi server có thể bảo đảm giá trị luôn tồn tại.
- Ưu tiên input object cho mutation có nhiều tham số liên quan.
- Thiết kế field lồng nhau có chủ đích; một operation có thể yêu cầu nhiều tầng dữ liệu và tạo tải lớn nếu server không kiểm soát.
- Khi thay đổi schema đang được sử dụng, thêm field mới thường ít ảnh hưởng hơn việc xóa hoặc đổi tên field hiện tại. Đánh dấu deprecated và cho client thời gian chuyển đổi trước khi loại bỏ field cũ.
- Không xem việc field có trong SDL là bằng chứng field đã được triển khai. Schema, handler và nguồn dữ liệu phải nhất quán.

## 9. Những lỗi thường gặp

| Tình huống | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| **Cannot query field ...** | Field không tồn tại trên type đang truy vấn | Kiểm tra đúng type và tên field trong schema |
| **Field ... must have a selection of subfields** | Field trả về object nhưng operation không chọn field con | Thêm selection set |
| **Field ... must not have a selection since type ... has no subfields** | Operation chọn field con của scalar hoặc enum | Bỏ selection set con |
| **Variable ... of required type ... was not provided** | Thiếu variable bắt buộc | Truyền variable hoặc điều chỉnh hợp đồng nếu nó thực sự không bắt buộc |
| **Variable ... is of type ... but used where ... is expected** | Kiểu variable không tương thích với argument | Đồng bộ kiểu khai báo variable với schema |
| Field có trong schema nhưng trả lỗi khi chạy | Chưa có handler phù hợp hoặc nguồn dữ liệu phát sinh lỗi | Kiểm tra mapping, service và exception |
| Response có field là **null** kèm **errors** | Field thực thi thất bại hoặc nullability buộc giá trị bị đẩy lên cha | Đọc **errors.path**, kiểm tra dữ liệu và thiết kế nullable |

## 10. Tổng kết

Schema định nghĩa hợp đồng kiểu dữ liệu và các điểm bắt đầu mà GraphQL API công bố. Operation sử dụng hợp đồng đó để yêu cầu đúng dữ liệu hoặc hành động cần thiết. SDL cung cấp object type, scalar, enum, input type, arguments, danh sách và nullability; Query, Mutation và Subscription xác định ba cách tương tác chính.

Trong Spring for GraphQL, schema được đặt trong tài nguyên của ứng dụng và các field được nối với method xử lý bằng những annotation tương ứng. Khi schema, operation và handler thống nhất, client có thể tự chọn dữ liệu cần nhận, còn server có một hợp đồng rõ ràng để kiểm tra, thực thi và tiến hóa API.

