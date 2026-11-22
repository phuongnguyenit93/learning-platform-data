# GraphQL type system

GraphQL type system là hệ thống kiểu định nghĩa dữ liệu mà một GraphQL API có thể nhận và trả về. Schema mô tả những kiểu dữ liệu tồn tại, các field của từng kiểu, tham số đầu vào, kiểu kết quả và những quan hệ mà client được phép truy vấn. Mỗi operation của client được kiểm tra dựa trên schema trước khi resolver thực thi.

Trong Spring for GraphQL, schema thường được khai báo bằng **Schema Definition Language (SDL)** trong các file **.graphqls** hoặc **.gqls**. Spring GraphQL kết hợp schema này với các Java method được đăng ký làm data fetcher, chẳng hạn qua **@QueryMapping**, **@MutationMapping** và **@SchemaMapping**. Cần phân biệt hai phần: GraphQL type system định nghĩa hợp đồng API; Java code cung cấp dữ liệu để thực hiện hợp đồng đó.

Sau bài này, bạn có thể đọc và thiết kế một schema có root type, scalar, object, enum, input object, interface, union, list và non-null; biết kiểu nào được dùng ở vị trí đầu vào hoặc đầu ra; đồng thời hiểu cách Spring for GraphQL nối schema với resolver.

## 1. Type system là hợp đồng giữa client và server

Một GraphQL server không công khai trực tiếp toàn bộ class, entity hoặc bảng trong cơ sở dữ liệu. Server công khai một schema có cấu trúc rõ ràng. Client chỉ được chọn những field đã khai báo trong schema và phải truyền các argument đúng kiểu.

Ví dụ, nếu schema khai báo:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
}
~~~

Client có thể yêu cầu **book**, truyền một **ID** bắt buộc và chọn các field **id**, **title** của kết quả. Client không thể tự yêu cầu field **internalCost** nếu field đó không có trong schema. Tương tự, server không thể trả về một giá trị có hình dạng tùy ý mà bỏ qua các quy tắc kiểu đã khai báo.

Schema mang lại ba lợi ích quan trọng:

- **Khả năng khám phá:** client và công cụ phát triển có thể biết API hỗ trợ kiểu, field, argument và mô tả nào.
- **Kiểm tra operation:** tên field, argument, biến và kiểu kết quả được kiểm tra trước khi resolver chạy.
- **Hợp đồng ổn định:** backend có thể thay đổi cách lưu trữ hoặc lấy dữ liệu mà không nhất thiết làm thay đổi schema công khai.

Type system không thay thế kiểm tra nghiệp vụ. Chẳng hạn, schema có thể bảo đảm **quantity** là số nguyên, nhưng việc số lượng đó có lớn hơn tồn kho hay người dùng có quyền đặt hàng hay không vẫn phải được xử lý trong tầng nghiệp vụ.

## 2. Khai báo schema bằng SDL

SDL là cú pháp văn bản dùng để mô tả schema. Một khai báo type thường có dạng:

~~~graphql
type TypeName {
  fieldName: FieldType
  anotherField(argument: ArgumentType): ReturnType
}
~~~

Tên type phân biệt chữ hoa và chữ thường. Theo quy ước phổ biến, tên type dùng PascalCase, tên field và argument dùng camelCase. Mỗi field có một kiểu trả về; field có thể nhận không hoặc nhiều argument.

### Root operation types

GraphQL có ba loại operation:

| Operation | Root type | Mục đích |
|---|---|---|
| Query | **Query** | Đọc dữ liệu |
| Mutation | **Mutation** | Thực hiện thay đổi dữ liệu |
| Subscription | **Subscription** | Nhận sự kiện hoặc cập nhật theo thời gian |

Một schema phải có root Query. Mutation và Subscription là tùy chọn. Nếu dùng tên mặc định **Query**, **Mutation**, **Subscription**, có thể không cần khai báo tường minh khối **schema**. Nếu muốn đặt tên root type khác, hãy khai báo:

~~~graphql
schema {
  query: ReadOperations
  mutation: WriteOperations
}

type ReadOperations {
  health: String!
}

type WriteOperations {
  refreshCache: Boolean!
}
~~~

Với Spring Boot và Spring for GraphQL, schema thường được đặt trong **src/main/resources/graphql/**, ví dụ **schema.graphqls** hoặc **books.graphqls**. Spring Boot tự tìm các file schema trong vị trí cấu hình mặc định và ghép các định nghĩa lại. Có thể chia schema theo nhóm nghiệp vụ; khi cần bổ sung field cho một type đã khai báo, SDL hỗ trợ cú pháp **extend type**.

Ví dụ, một file có thể định nghĩa **type Query**, còn file khác bổ sung:

~~~graphql
extend type Query {
  recentBooks(limit: Int = 10): [Book!]!
}
~~~

Các file vẫn tạo thành một schema thống nhất. Tên type được định nghĩa ở một nơi; các phần mở rộng phải tham chiếu đúng type đã tồn tại.

## 3. Các nhóm named type

GraphQL có sáu nhóm named type chính: scalar, object, enum, input object, interface và union. Mỗi nhóm có mục đích và vị trí sử dụng khác nhau.

### Scalar: giá trị đơn

Scalar biểu diễn một giá trị nguyên tử. GraphQL định nghĩa sẵn năm scalar:

| Scalar | Ý nghĩa |
|---|---|
| **Int** | Số nguyên có dấu 32-bit |
| **Float** | Số thực dấu phẩy động |
| **String** | Chuỗi ký tự |
| **Boolean** | Giá trị đúng hoặc sai |
| **ID** | Định danh; thường được serialize thành chuỗi |

**ID** dành cho định danh và không hàm ý kiểu dữ liệu của khóa chính trong cơ sở dữ liệu. Một ID có thể là UUID, mã nghiệp vụ hoặc giá trị opaque do server quản lý. Không nên dùng **Int** cho định danh chỉ vì khóa chính hiện tại là số.

GraphQL không có sẵn các kiểu như **Date**, **DateTime**, **Decimal**, **Long** hoặc **UUID**. Khi API cần chúng, ta khai báo custom scalar:

~~~graphql
scalar DateTime
scalar Money
~~~

Khai báo **scalar** trong SDL mới chỉ đặt tên kiểu trong schema. Server còn phải cung cấp cách chuyển đổi và xác thực giá trị ở runtime. Phần tích hợp với Spring for GraphQL được trình bày ở mục 8.

### Object type: cấu trúc dữ liệu đầu ra

Object type mô tả một đối tượng có các field. Ví dụ:

~~~graphql
type Book {
  id: ID!
  title: String!
  publishedAt: DateTime
}
~~~

Một object type có thể chứa field scalar, enum hoặc field tham chiếu đến object/interface/union khác. Field tham chiếu tạo thành quan hệ có thể truy vấn lồng nhau:

~~~graphql
type Book {
  id: ID!
  title: String!
  author: Author!
}

type Author {
  id: ID!
  name: String!
}
~~~

Client có thể lấy sách và tác giả trong cùng một operation:

~~~graphql
query {
  book(id: "book-01") {
    title
    author {
      id
      name
    }
  }
}
~~~

Quan hệ trong schema chỉ mô tả hình dạng API. Nó không tự tạo quan hệ trong cơ sở dữ liệu, cũng không bảo đảm việc lấy dữ liệu có hiệu quả. Resolver của field **author** vẫn phải được thực thi hoặc được cung cấp bởi property data fetcher.

Field cũng có thể nhận argument. Điều này cho phép biểu diễn bộ lọc hoặc tham số truy vấn tại đúng nơi sử dụng:

~~~graphql
type Query {
  books(status: BookStatus, limit: Int = 20): [Book!]!
}
~~~

### Enum: tập giá trị hữu hạn

Enum giới hạn giá trị của một field hoặc argument vào một tập tên đã định nghĩa:

~~~graphql
enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

type Book {
  id: ID!
  status: BookStatus!
}
~~~

Enum phù hợp với những tập lựa chọn hữu hạn và có ý nghĩa rõ ràng, chẳng hạn trạng thái đơn hàng, vai trò hoặc loại phương thức giao hàng. Nó giúp client phát hiện lỗi chính tả và tạo kiểu dữ liệu an toàn hơn so với việc dùng **String** cho mọi giá trị.

Giá trị enum trong operation được gửi dưới dạng enum literal, không đặt trong dấu nháy:

~~~graphql
query {
  books(status: PUBLISHED) {
    id
    title
  }
}
~~~

Khi truyền qua variables JSON, giá trị enum được biểu diễn bằng chuỗi tương ứng, ví dụ **{"status":"PUBLISHED"}**. Việc thêm một enum value có thể ảnh hưởng client đang xử lý enum theo kiểu exhaustive, vì vậy cần cân nhắc khả năng tương thích khi mở rộng enum.

### Input object: cấu trúc dữ liệu đầu vào

Input object gom nhiều giá trị đầu vào thành một cấu trúc. Nó thường được dùng cho argument của mutation:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
  status: BookStatus = DRAFT
  publishedAt: DateTime
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
~~~

Client truyền input object qua variables:

~~~graphql
mutation CreateBook($input: CreateBookInput!) {
  createBook(input: $input) {
    id
    title
    status
  }
}
~~~

Variables:

~~~json
{
  "input": {
    "title": "GraphQL with Spring",
    "authorId": "author-01",
    "status": "DRAFT"
  }
}
~~~

Input object có thể chứa scalar, enum, input object khác và các kiểu bọc như list/non-null. Nó không thể chứa object type, interface hoặc union. GraphQL cần phân biệt rõ dữ liệu client được phép gửi với dữ liệu server trả về; vì thế không thể dùng một object type thông thường làm kiểu input cho mutation.

Không nên mặc định dùng một input object cho mọi thao tác cập nhật. Ví dụ **CreateBookInput** và **UpdateBookInput** thường có quy tắc bắt buộc khác nhau. Tách chúng giúp schema thể hiện đúng ý nghĩa của từng operation.

### Interface: hợp đồng field dùng chung

Interface định nghĩa các field mà nhiều object type cam kết cung cấp:

~~~graphql
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
~~~

Khi một field trả về **Node**, client có thể truy vấn các field được khai báo trên interface, chẳng hạn **id**. Muốn lấy field riêng của một kiểu cụ thể, client dùng inline fragment:

~~~graphql
query {
  node(id: "item-01") {
    id
    __typename
    ... on Book {
      title
    }
    ... on Author {
      name
    }
  }
}
~~~

Object triển khai interface phải cung cấp các field mà interface yêu cầu với kiểu tương thích theo quy tắc của GraphQL. Interface hữu ích khi nhiều kiểu có cùng một khả năng hoặc thuộc tính chung, nhưng vẫn cần giữ các field chuyên biệt.

### Union: một trong nhiều object type

Union biểu diễn kết quả có thể thuộc một trong nhiều object type, mà không yêu cầu các object phải có field chung:

~~~graphql
union SearchResult = Book | Author

type Query {
  search(term: String!): [SearchResult!]!
}
~~~

Vì union không khai báo tập field chung, client phải dùng inline fragment để chọn field của từng kiểu:

~~~graphql
query Search($term: String!) {
  search(term: $term) {
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

Union chỉ liệt kê object type làm thành viên. Nếu các kiểu kết quả có một tập field chung thực sự cần truy vấn trực tiếp, interface có thể phù hợp hơn. Nếu chúng chỉ là các kết quả khác loại trong cùng một use case, union thường diễn tả ý định rõ ràng.

## 4. Input type và output type

Một lỗi thiết kế thường gặp là dùng nhầm object type ở vị trí input hoặc dùng input object làm kiểu trả về. GraphQL phân loại kiểu theo hướng dữ liệu:

| Vị trí trong schema | Kiểu được phép |
|---|---|
| Output: kiểu trả về của field | Scalar, enum, object, interface, union |
| Input: argument hoặc biến đầu vào | Scalar, enum, input object |

List và non-null có thể bọc một kiểu hợp lệ ở cả hai phía. Ví dụ:

- **Book** là output type; có thể là kiểu trả về của field.
- **CreateBookInput** là input type; có thể là kiểu của argument.
- **[ID!]!** là input type hợp lệ vì nó bọc scalar **ID**.
- **[Book!]!** là output type hợp lệ vì nó bọc object **Book**.

Schema sau không hợp lệ vì dùng object type làm input:

~~~graphql
type Query {
  findBook(filter: Book): Book
}
~~~

Nếu cần gửi bộ lọc, hãy định nghĩa input object:

~~~graphql
input BookFilter {
  titleContains: String
  status: BookStatus
}

type Query {
  findBooks(filter: BookFilter): [Book!]!
}
~~~

Tương tự, không khai báo field trả về **CreateBookInput**; hãy trả về object type thể hiện dữ liệu mà client được phép đọc.

## 5. List và Non-Null: hiểu chính xác khả năng null

GraphQL dùng hai wrapper type:

- List **[...]** biểu diễn một danh sách.
- Non-Null **!** khẳng định giá trị tại vị trí đó không được là **null**.

Hai wrapper có thể kết hợp và thứ tự bọc làm thay đổi ý nghĩa:

| Khai báo | Danh sách có thể null? | Phần tử có thể null? |
|---|---:|---:|
| **[Book]** | Có | Có |
| **[Book]!** | Không | Có |
| **[Book!]** | Có | Không |
| **[Book!]!** | Không | Không |

Với scalar, **String** có thể là **null**, còn **String!** phải luôn có giá trị:

~~~graphql
type Profile {
  displayName: String!
  biography: String
}
~~~

Ở đây **displayName** bắt buộc có giá trị; **biography** có thể vắng mặt hoặc chưa được cung cấp và được trả về là **null**. Dấu **!** không có nghĩa là client bắt buộc phải chọn field trong query. Nó là cam kết về giá trị mà server trả về, hoặc về giá trị đầu vào mà schema yêu cầu.

### Non-null ở đầu vào

Với argument **id: ID!**, client phải cung cấp argument và giá trị không được là **null**:

~~~graphql
type Query {
  book(id: ID!): Book
}
~~~

Nếu thiếu argument hoặc truyền **null**, operation không hợp lệ đối với schema. Một argument có giá trị mặc định có thể không cần được client truyền:

~~~graphql
type Query {
  books(limit: Int = 20): [Book!]!
}
~~~

Nếu client bỏ qua **limit**, server sử dụng giá trị mặc định **20**. Với input object, field có thể được đánh dấu non-null hoặc có giá trị mặc định theo cùng nguyên tắc.

### Non-null ở đầu ra và null propagation

Khi resolver trả về **null** cho field non-null, GraphQL tạo execution error và lan truyền **null** lên field cha gần nhất có thể nhận **null**. Quá trình này thường được gọi là null propagation hoặc null bubbling.

Ví dụ:

~~~graphql
type Book {
  id: ID!
  author: Author!
}

type Query {
  book(id: ID!): Book
}
~~~

Nếu resolver của **Book.author** trả về **null**, field **author** vi phạm hợp đồng **Author!**. GraphQL phải làm **Book** cha thành **null**. Vì **Query.book** cho phép null, kết quả cuối cùng có thể là **book: null** kèm lỗi trong phần **errors**.

Nếu cùng field **book** được khai báo **Book!**, lỗi sẽ tiếp tục lan lên root result. Với danh sách **[Book!]!**, một phần tử không thể là null; nếu một phần tử vi phạm, cả danh sách bị null hóa, sau đó do danh sách cũng non-null, lỗi tiếp tục lan lên cha.

Do đó, chọn non-null là quyết định thiết kế có ảnh hưởng đến khả năng phục hồi của response. Chỉ dùng **!** khi server thực sự có thể bảo đảm giá trị trong mọi tình huống hợp lệ. Một field phụ thuộc vào dịch vụ bên ngoài hoặc dữ liệu có thể không tồn tại có thể cần được khai báo nullable, tùy hợp đồng nghiệp vụ.

## 6. Ví dụ schema hoàn chỉnh

Ví dụ sau kết hợp các nhóm type thường gặp trong một API quản lý sách:

~~~graphql
scalar DateTime

enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

interface Node {
  id: ID!
}

type Book implements Node {
  id: ID!
  title: String!
  status: BookStatus!
  publishedAt: DateTime
  author: Author!
  tags: [String!]!
  legacyCode: String @deprecated(reason: "Sử dụng id")
}

type Author implements Node {
  id: ID!
  name: String!
  books: [Book!]!
}

union SearchResult = Book | Author

input CreateBookInput {
  title: String!
  authorId: ID!
  status: BookStatus = DRAFT
  publishedAt: DateTime
}

type Query {
  book(id: ID!): Book
  node(id: ID!): Node
  books(status: BookStatus, limit: Int = 20): [Book!]!
  search(term: String!): [SearchResult!]!
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
~~~

Schema này thể hiện một số quyết định:

- **Query.book** trả về **Book** nullable vì mã sách có thể không tồn tại.
- **Query.books** trả về list non-null, và mỗi phần tử cũng non-null. Một truy vấn thành công phải có một danh sách; từng phần tử phải là một **Book**.
- **Book.author** là non-null, nghĩa là mỗi sách được trả về phải có tác giả hợp lệ theo hợp đồng API.
- **publishedAt** nullable vì sách nháp có thể chưa có ngày xuất bản.
- **CreateBookInput** dùng **authorId** để client chỉ định tác giả; server quyết định cách tải và liên kết tác giả.
- **SearchResult** cho phép kết quả tìm kiếm là sách hoặc tác giả.
- **legacyCode** được đánh dấu deprecated để báo client chuyển sang dùng **id**.

Một query dùng interface và union có thể viết:

~~~graphql
query SearchCatalog($term: String!, $id: ID!) {
  node(id: $id) {
    id
    __typename
    ... on Book {
      title
      status
    }
    ... on Author {
      name
    }
  }
  search(term: $term) {
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

**__typename** là meta-field do GraphQL cung cấp, trả về tên object type cụ thể tại runtime. Nó hữu ích khi client cần phân biệt các kiểu kết quả, đặc biệt với interface và union.

## 7. Cách GraphQL kiểm tra operation

Giả sử schema có field:

~~~graphql
type Query {
  book(id: ID!): Book
}
~~~

Operation sau hợp lệ về mặt kiểu:

~~~graphql
query FindBook($id: ID!) {
  book(id: $id) {
    id
    title
  }
}
~~~

Operation sau không hợp lệ vì **Book** không khai báo field **name**:

~~~graphql
query FindBook($id: ID!) {
  book(id: $id) {
    name
  }
}
~~~

Operation sau cũng không hợp lệ vì biến **id** có kiểu nullable **ID**, trong khi argument yêu cầu **ID!**:

~~~graphql
query FindBook($id: ID) {
  book(id: $id) {
    id
  }
}
~~~

Những lỗi này được phát hiện trong giai đoạn validation, trước khi resolver lấy dữ liệu. Khi thiết kế schema, hãy xem các lỗi validation như một phần của hợp đồng: chúng giúp client phát hiện sớm cách gọi API sai.

## 8. Kết nối type system với Spring for GraphQL

Trong Spring for GraphQL, SDL mô tả field và kiểu dữ liệu; controller cung cấp logic lấy giá trị cho các field. Ví dụ, với phần schema:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  author: Author!
}
~~~

Controller có thể triển khai root field và field quan hệ:

~~~java
@Controller
public class BookGraphQlController {

    private final BookService bookService;
    private final AuthorService authorService;

    public BookGraphQlController(
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
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }
}
~~~

**@QueryMapping** ánh xạ method **book** vào field **Query.book**. **@Argument** lấy argument **id** từ operation. **@SchemaMapping** ánh xạ method **author** vào field **Book.author**; tham số **Book** là source object mà field đang được resolve.

Tên Java class không tự định nghĩa GraphQL type. **Book** trong SDL là tên type của schema; **Book** trong tham số method là kiểu Java mà resolver nhận. Hai bên cần được ánh xạ nhất quán, nhưng không bắt buộc mô hình Java phải giống hệt cấu trúc schema. Nếu source object đã có property phù hợp, GraphQL Java có thể đọc property đó bằng property data fetcher mặc định mà không cần viết resolver riêng.

Các root field còn lại được ánh xạ tương ứng bằng **@MutationMapping** và **@SubscriptionMapping**. Với field quan hệ được gọi trên nhiều object, resolver đơn giản có thể tạo ra nhiều truy vấn dữ liệu. **@BatchMapping** hoặc DataLoader là những cơ chế để gom các lần tải dữ liệu, giúp xử lý vấn đề N+1; đó là tối ưu ở tầng thực thi, còn schema vẫn giữ nguyên hợp đồng kiểu.

### Đăng ký custom scalar

Với **DateTime** trong ví dụ schema, server cần một scalar implementation để chuyển đổi giữa giá trị GraphQL và kiểu Java. Có thể dùng thư viện GraphQL Java Extended Scalars và đăng ký scalar qua **RuntimeWiringConfigurer**. Sau khi thêm dependency tương ứng, cấu hình có thể có dạng:

~~~java
@Configuration
public class GraphQlScalarConfiguration {

    @Bean
    RuntimeWiringConfigurer runtimeWiringConfigurer() {
        return wiringBuilder ->
                wiringBuilder.scalar(ExtendedScalars.DateTime);
    }
}
~~~

**scalar DateTime** trong SDL và **ExtendedScalars.DateTime** trong runtime wiring phải cùng tên. Scalar implementation chịu trách nhiệm serialize giá trị trả về và parse giá trị đầu vào từ variables hoặc literal. Nếu cần định dạng ngày giờ riêng của hệ thống, có thể xây dựng **GraphQLScalarType** với **Coercing** phù hợp, đồng thời xác thực dữ liệu sai định dạng và quy tắc múi giờ.

### Resolve interface và union

Khi resolver trả về một field có kiểu interface hoặc union, GraphQL cần biết object type cụ thể của từng giá trị tại runtime. Ví dụ, **SearchResult** có thể nhận một Java object **Book** hoặc **Author**. GraphQL Java sử dụng **TypeResolver** để xác định object type tương ứng.

Nếu cơ chế phân giải mặc định không nhận diện được các kiểu Java trong ứng dụng, hãy đăng ký type resolver qua **RuntimeWiringConfigurer** cho interface hoặc union tương ứng. Resolver cần trả về đúng GraphQL object type đã khai báo trong SDL. Việc khai báo **union SearchResult = Book | Author** mới mô tả các thành viên hợp lệ; nó không tự quyết định một object Java cụ thể thuộc thành viên nào.

## 9. Directive và introspection

Directive bổ sung chỉ dẫn cho schema hoặc operation. GraphQL có các directive chuẩn thường gặp:

| Directive | Công dụng |
|---|---|
| **@skip(if: Boolean!)** | Bỏ qua field hoặc fragment khi điều kiện đúng |
| **@include(if: Boolean!)** | Chỉ đưa field hoặc fragment vào response khi điều kiện đúng |
| **@deprecated(reason: String)** | Đánh dấu field hoặc enum value đã lỗi thời |
| **@specifiedBy(url: String!)** | Gắn tài liệu đặc tả cho custom scalar |

Ví dụ đánh dấu field cũ:

~~~graphql
type Book {
  id: ID!
  legacyCode: String @deprecated(reason: "Sử dụng id")
}
~~~

Client vẫn có thể truy vấn field deprecated trong giai đoạn chuyển đổi, nhưng schema tooling có thể hiển thị cảnh báo để khuyến khích chuyển sang field mới.

GraphQL còn cung cấp introspection để client hoặc công cụ khám phá schema. **__schema** và **__type** cho phép truy vấn metadata về schema; **__typename** cho biết object type cụ thể của một giá trị. Introspection giúp IDE và công cụ sinh client hiểu API mà không cần đọc mã nguồn server.

Directive không thay thế authorization. Chẳng hạn, ẩn một field khỏi tài liệu hoặc bỏ qua field ở client không bảo đảm người dùng không thể gọi field đó. Quyền truy cập phải được kiểm tra ở server, tại resolver hoặc lớp bảo mật thích hợp.

## 10. Tiến hóa schema an toàn

Schema là hợp đồng công khai nên thay đổi type có thể ảnh hưởng các client đang hoạt động. Một số nguyên tắc thực tế:

- **Ưu tiên mở rộng tương thích:** thêm field nullable thường ít gây ảnh hưởng hơn thêm field non-null bắt buộc.
- **Thận trọng khi thêm argument bắt buộc:** client cũ chưa truyền argument mới có thể không còn gọi được operation.
- **Không xóa field ngay:** đánh dấu **@deprecated**, thông báo lý do và cho client thời gian chuyển đổi trước khi loại bỏ.
- **Cân nhắc khi thêm enum value:** client có thể dùng switch exhaustive hoặc giả định chỉ tồn tại tập giá trị cũ.
- **Không phơi bày cấu trúc persistence một cách máy móc:** schema nên phản ánh nhu cầu của client và ngôn ngữ nghiệp vụ, không nhất thiết trùng entity hoặc bảng.
- **Chọn nullability theo cam kết dữ liệu:** thay đổi từ nullable sang non-null hoặc ngược lại đều có thể làm thay đổi hành vi client và cách lỗi lan truyền.

Ví dụ, nếu trước đây schema có:

~~~graphql
type Book {
  id: ID!
  subtitle: String
}
~~~

Thêm một field mới nullable thường cho phép client cũ tiếp tục hoạt động:

~~~graphql
type Book {
  id: ID!
  subtitle: String
  language: String
}
~~~

Trong khi đó, thêm **language: String!** buộc mọi đường thực thi trả về **Book** phải cung cấp giá trị. Nếu dữ liệu cũ chưa có ngôn ngữ hoặc resolver không thể xác định, field mới có thể gây lỗi runtime và null propagation.

## 11. Những lỗi thiết kế thường gặp

| Vấn đề | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dùng **type** làm argument | Object type là output type | Khai báo **input** riêng |
| Dùng input object làm kiểu trả về | Input object chỉ dành cho dữ liệu đầu vào | Trả về object type |
| Đánh dấu mọi field là non-null | Chưa đánh giá trường hợp dữ liệu thiếu hoặc lỗi phụ thuộc | Chọn nullability theo cam kết nghiệp vụ |
| Dùng **String** cho mọi lựa chọn | Không giới hạn tập giá trị | Dùng enum khi tập giá trị hữu hạn |
| Khai báo custom scalar nhưng thiếu runtime wiring | SDL chỉ khai báo tên scalar | Đăng ký scalar implementation |
| Trả về interface/union nhưng không phân giải được object type | Runtime không biết object cụ thể | Cấu hình **TypeResolver** |
| Field quan hệ chạy một truy vấn cho mỗi object | Resolver tải dữ liệu riêng lẻ | Xem xét **@BatchMapping** hoặc DataLoader |
| Thêm field non-null nhưng dữ liệu không bảo đảm | Schema hứa mạnh hơn khả năng của hệ thống | Bổ sung dữ liệu/logic hoặc thiết kế nullable phù hợp |

## 12. Quy trình đọc và thiết kế một schema

Khi đọc một schema có sẵn hoặc thiết kế schema mới, có thể đi theo trình tự:

1. Xác định root Query, Mutation và Subscription để hiểu các điểm vào API.
2. Lần theo các object type được trả về từ root field để thấy cấu trúc dữ liệu client có thể đọc.
3. Phân biệt scalar, enum, interface và union để hiểu loại giá trị có thể xuất hiện.
4. Kiểm tra input object và argument để biết client phải gửi dữ liệu gì.
5. Đọc kỹ từng dấu **!** và cặp ngoặc list để xác định chỗ nào có thể null.
6. Tìm custom scalar và directive để xác định các quy tắc bổ sung.
7. Đối chiếu các field với resolver Spring GraphQL để biết dữ liệu được lấy như thế nào và kiểu cụ thể được phân giải ra sao.
8. Kiểm tra operation mẫu bằng **GraphQlTester** hoặc công cụ GraphQL phù hợp để phát hiện lỗi schema và validation.

Một schema tốt diễn đạt được dữ liệu mà client cần, giới hạn đầu vào hợp lệ và đưa ra cam kết nullability mà server có thể thực hiện. Trong Spring for GraphQL, khi đã nắm type system, việc viết resolver trở nên rõ ràng hơn: mỗi method phục vụ một field hoặc một nhóm field đã có hợp đồng cụ thể, còn logic nghiệp vụ và chiến lược tải dữ liệu được triển khai ở phía server.
