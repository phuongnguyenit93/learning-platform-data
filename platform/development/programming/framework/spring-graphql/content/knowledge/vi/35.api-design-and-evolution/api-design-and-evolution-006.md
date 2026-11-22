# Thay đổi nullability trong GraphQL schema

Nullability là một phần của hợp đồng GraphQL giữa server và client. Dấu `!` trong SDL cho biết một giá trị không được phép là `null`; khi thay đổi dấu này, server có thể thay đổi dữ liệu trả về, điều kiện đầu vào hoặc cách lỗi lan truyền trong response. Vì vậy, thay đổi nullability cần được xem như một thay đổi API có ảnh hưởng đến client và resolver.

GraphQL mặc định cho phép field trả về `null`. Non-Null chỉ nên được khai báo khi server có thể bảo đảm giá trị luôn tồn tại trong mọi tình huống hợp lệ. Với Spring for GraphQL, SDL định nghĩa hợp đồng này; resolver và service phải thực hiện đúng cam kết đó.

## Nullability trong GraphQL có nghĩa gì?

Trong SDL, kiểu không có `!` là nullable. Kiểu có `!` là Non-Null:

```graphql
type User {
  id: ID!
  displayName: String
  manager: User
}
```

`id` phải luôn có giá trị khi field được yêu cầu. `displayName` và `manager` có thể trả về `null`. Nếu client không chọn một field, field đó không xuất hiện trong response; nếu client chọn một field nullable nhưng server không có giá trị, response chứa field với giá trị `null`.

Không đồng nhất `null` với chuỗi rỗng, danh sách rỗng hoặc field không được chọn:

| Giá trị | Ý nghĩa |
| --- | --- |
| `null` | Không có giá trị hoặc không thể cung cấp giá trị theo ngữ nghĩa của field. |
| `""` | Có một chuỗi, nhưng chuỗi rỗng. |
| `[]` | Có một danh sách hợp lệ với zero phần tử. |
| Field không xuất hiện | Client không yêu cầu field đó hoặc directive khiến field bị bỏ qua. |

Non-Null không có nghĩa field luôn có dữ liệu trong database. Nó là cam kết ở cấp API: khi field được yêu cầu, server phải trả giá trị không null; nếu không làm được, GraphQL tạo execution error.

## Nullability của list và phần tử list

Với list, dấu `!` có thể áp dụng cho chính list hoặc cho từng phần tử. Hai vị trí này độc lập:

| SDL | List có thể null? | Phần tử có thể null? | Giá trị hợp lệ ví dụ |
| --- | --- | --- | --- |
| `[Book]` | Có | Có | `null`, `[]`, `[null]`, `[book]` |
| `[Book]!` | Không | Có | `[]`, `[null]`, `[book]` |
| `[Book!]` | Có | Không | `null`, `[]`, `[book]` |
| `[Book!]!` | Không | Không | `[]`, `[book]` |

Ví dụ:

```graphql
type Author {
  booksA: [Book]
  booksB: [Book]!
  booksC: [Book!]
  booksD: [Book!]!
}
```

`booksB` bảo đảm luôn trả về một list nhưng list vẫn có thể chứa phần tử null. `booksC` cho phép cả list là null nhưng không cho phép phần tử null. `booksD` bảo đảm cả list và từng phần tử đều khác null.

`[Book!]!` vẫn cho phép `[]`. GraphQL Non-Null chỉ cấm giá trị null; nó không thể diễn tả yêu cầu danh sách phải có ít nhất một phần tử. Nếu nghiệp vụ cần danh sách không rỗng, kiểm tra ở service hoặc dùng một kiểu payload có field thể hiện trạng thái và dữ liệu.

## Null propagation khi resolver vi phạm Non-Null

Khi resolver trả `null` cho field Non-Null, GraphQL tạo execution error và đẩy giá trị null lên parent response position. Quá trình tiếp tục cho tới khi gặp một vị trí nullable; nếu không có vị trí nullable nào trước root, toàn bộ `data` trở thành null.

Ví dụ schema:

```graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  author: Author!
}

type Author {
  id: ID!
  name: String!
}
```

Nếu `book` tồn tại nhưng resolver `author` trả null, GraphQL không thể trả `author: null` vì field là `Author!`. Error path chỉ ra field `book.author`, còn `book` trở thành null vì đó là parent nullable gần nhất:

```json
{
  "data": {
    "book": null
  },
  "errors": [
    {
      "message": "Cannot return null for non-nullable field Book.author.",
      "path": ["book", "author"]
    }
  ]
}
```

Nếu `Query.book` cũng là `Book!`, null tiếp tục lan lên root và response có `data: null`. Đây là lý do thay đổi một field từ nullable sang Non-Null có thể làm mất nhiều dữ liệu hơn field đang lỗi.

### Null trong list

Với `books: [Book]`, một phần tử null được giữ tại đúng vị trí:

```json
{
  "data": {
    "books": [
      { "id": "book-1" },
      null,
      { "id": "book-3" }
    ]
  }
}
```

Với `books: [Book!]`, phần tử null vi phạm item type Non-Null. GraphQL tạo error và toàn bộ list trở thành null; vì list itself nullable, response vẫn có thể giữ các field khác:

```json
{
  "data": {
    "books": null
  },
  "errors": [
    {
      "message": "Cannot return null for non-nullable list item.",
      "path": ["books", 1]
    }
  ]
}
```

Với `books: [Book!]!`, lỗi phần tử làm list null, sau đó Non-Null của list tiếp tục đẩy null lên parent. Khi thiết kế list type, hãy cân nhắc mức độ cô lập lỗi cần có: cho phép một item null có thể giữ lại các item còn lại; bắt buộc item non-null có thể làm mất cả list khi một phần tử lỗi.

## Nullability của output field và input

Quy tắc Non-Null khác nhau giữa dữ liệu trả về và dữ liệu client gửi vào:

| Vị trí | Nullable | Non-Null (`!`) |
| --- | --- | --- |
| Output field | Server có thể trả `null`. | Server cam kết không trả `null` khi field được yêu cầu. |
| Field argument | Client có thể bỏ qua hoặc truyền `null` nếu không có quy tắc khác. | Client phải cung cấp giá trị khác null, trừ trường hợp có default value cho phép bỏ qua. |
| Input object field | Field có thể bị bỏ qua hoặc truyền `null`. | Field phải được cung cấp và khác null nếu không có default value. |

Ví dụ input:

```graphql
input CreateBookInput {
  title: String!
  subtitle: String
  authorId: ID!
  publishedAt: String
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
```

Client phải cung cấp `title` và `authorId`. Client có thể bỏ qua `subtitle`/`publishedAt` hoặc truyền null cho các field nullable đó. Nếu input object field Non-Null có default value, field có thể được bỏ qua và GraphQL dùng default; explicit null vẫn không hợp lệ.

### Omitted và explicit null không giống nhau

Với input field nullable, hai request sau đều hợp lệ nhưng mang ý nghĩa khác nhau:

```graphql
# Không gửi subtitle
mutation {
  createBook(input: { title: "GraphQL", authorId: "author-1" }) { id }
}

# Gửi subtitle rõ ràng là null
mutation {
  createBook(input: { title: "GraphQL", subtitle: null, authorId: "author-1" }) { id }
}
```

Với API cập nhật, omitted thường có nghĩa là giữ nguyên giá trị cũ; explicit null có thể có nghĩa là xóa giá trị. Nếu Java DTO chỉ dùng `String subtitle`, cả hai trường hợp có thể cùng trở thành null sau binding và làm mất thông tin client đã gửi gì.

Spring for GraphQL có `ArgumentValue<T>` để giữ sự khác biệt giữa field bị omitted và field được gửi với null:

```java
import org.springframework.graphql.data.ArgumentValue;

public record UpdateBookInput(
        String id,
        ArgumentValue<String> subtitle) {
}
```

```java
@MutationMapping
public Book updateBook(@Argument("input") UpdateBookInput input) {
    if (input.subtitle().isOmitted()) {
        return bookService.keepSubtitle(input.id());
    }

    if (input.subtitle().value() == null) {
        return bookService.clearSubtitle(input.id());
    }

    return bookService.changeSubtitle(input.id(), input.subtitle().value());
}
```

Để serialize optional input trên client, cấu hình module GraphQL Jackson tương ứng với major version Jackson mà transport sử dụng (`GraphQlJacksonModule` hoặc `GraphQlJackson2Module`) trên đúng mapper/encoder. Với server-side argument binding, dùng `ArgumentValue` khi nghiệp vụ cần phân biệt hai trạng thái này.

## Thay đổi nullability có tương thích ngược không?

Không thể đánh giá thay đổi nullability chỉ bằng việc có thêm hoặc bớt dấu `!`. Phải xét field nằm ở output hay input, list wrapper hay item type, và client thực tế đang gửi/đọc dữ liệu thế nào.

### Output: nullable thành Non-Null

Ví dụ:

```graphql
# Trước
type User {
  displayName: String
}

# Sau
type User {
  displayName: String!
}
```

Đây là thay đổi thu hẹp tập giá trị server có thể trả về. Với client GraphQL, đây thường là thay đổi tương thích vì client trước đó đã phải chấp nhận `String` hoặc null; server nay cam kết chỉ trả string. Tuy nhiên, nó chỉ an toàn khi resolver thực sự bảo đảm non-null trong mọi trường hợp hợp lệ.

Rủi ro vận hành: dữ liệu cũ có thể null, service có thể không tìm thấy quan hệ, authorization có thể che field, hoặc downstream có thể lỗi. Khi một trong các trường hợp đó trả null, GraphQL tạo error và null propagation có thể làm null cả object/list cha. Vì vậy đây là thay đổi an toàn về kiểu khi có đủ bằng chứng dữ liệu, nhưng không phải thao tác chỉ sửa SDL.

### Output: Non-Null thành nullable

Ví dụ:

```graphql
# Trước
type Order {
  discount: Float!
}

# Sau
type Order {
  discount: Float
}
```

Đây là thay đổi nới rộng tập giá trị server có thể trả về. Client cũ có thể đã sinh kiểu Java/Kotlin/TypeScript không nullable và dereference trực tiếp field. Khi server bắt đầu trả null, client có thể lỗi runtime hoặc phải thay đổi logic. Đây thường là breaking change.

### Input: nullable thành Non-Null

Ví dụ:

```graphql
# Trước
input UpdateBookInput {
  authorId: ID
}

# Sau
input UpdateBookInput {
  authorId: ID!
}
```

Client cũ có thể bỏ qua `authorId` hoặc gửi explicit null. Sau thay đổi, operation có thể thất bại ở validation/coercion trước khi resolver chạy. Đây là breaking change với input contract.

### Input: Non-Null thành nullable

Ví dụ:

```graphql
# Trước
input CreateBookInput {
  authorId: ID!
}

# Sau
input CreateBookInput {
  authorId: ID
}
```

Đây là thay đổi nới lỏng điều kiện đầu vào: client cũ vẫn có thể gửi giá trị như trước; client mới có thể bỏ qua hoặc gửi null. Thay đổi thường tương thích ngược, nhưng server phải định nghĩa hành vi khi field vắng mặt hoặc null. Nếu nghiệp vụ vẫn cần tác giả, validation/domain layer cần trả lỗi có chủ đích thay vì để hành vi trở nên mơ hồ.

## Ma trận tương thích ngược

| Thay đổi | Tác động chính | Đánh giá thông thường |
| --- | --- | --- |
| Output `T` → `T!` | Server cam kết mạnh hơn; client nhận ít khả năng null hơn. | Thường tương thích nếu resolver/data thực sự luôn non-null. |
| Output `T!` → `T` | Client có thể nhận null mà trước đây schema không cho phép. | Breaking change. |
| Input `T` → `T!` | Client phải cung cấp giá trị khác null. | Breaking change. |
| Input `T!` → `T` | Client được phép bỏ qua hoặc gửi null. | Thường tương thích; cần định nghĩa semantics mới. |
| Output list `[T]` → `[T!]` | Phần tử null không còn hợp lệ; list vẫn có thể null. | Thường tương thích nếu không có item null. |
| Output list `[T]` → `[T]!` | List không còn được null; item vẫn có thể null. | Thường tương thích nếu resolver luôn trả list. |
| Output `[T!]!` → `[T]` | Cả list và item có thể null trở lại. | Breaking change với client dựa vào guarantee cũ. |
| Input `[T]` → `[T!]` hoặc `[T]!` | Giới hạn thêm giá trị client được phép gửi. | Breaking change nếu client gửi null list/item. |
| Input `[T!]!` → `[T]` | Cho phép client bỏ list hoặc gửi item null. | Thường tương thích; server cần định nghĩa cách xử lý các giá trị mới được phép. |

Đây là phân loại ở cấp hợp đồng GraphQL. Schema check của nền tảng có thể gắn nhãn thay đổi type và đánh giá operation cụ thể dựa trên lịch sử sử dụng. Với output nullable thành Non-Null, công cụ vẫn có thể cảnh báo `FIELD_CHANGED_TYPE`; hãy kiểm tra resolver, dữ liệu và operation impact trước khi duyệt thay đổi.

## Thay đổi nullability an toàn theo chiến lược expand-contract

Không nên đổi nullable thành Non-Null chỉ vì database column hiện được khai báo `NOT NULL`. API có thể có nhiều nguồn dữ liệu và resolver khác nhau; null vẫn có thể phát sinh từ authorization, downstream failure, mapping hoặc dữ liệu lịch sử.

Một quy trình thay đổi output nullable thành Non-Null:

1. **Đo hiện trạng:** tìm các bản ghi null, số lần resolver trả null và các error liên quan trong production.
2. **Sửa dữ liệu:** backfill hoặc làm sạch dữ liệu cũ theo quy tắc nghiệp vụ.
3. **Sửa resolver/service:** bảo đảm mọi đường đi trả giá trị hợp lệ; xử lý rõ trường hợp không có dữ liệu.
4. **Kiểm thử:** test dữ liệu cũ, dữ liệu mới, missing relation, lỗi downstream và authorization.
5. **Theo dõi:** triển khai resolver mới trước, quan sát null/error rate trong thời gian đủ dài.
6. **Siết schema:** chỉ đổi `T` thành `T!` sau khi có bằng chứng rằng cam kết mới luôn được đáp ứng.

Với output Non-Null thành nullable, nếu cần nới lỏng contract thì nên thêm field mới nullable, giữ field cũ để client chuyển đổi, đánh dấu field cũ deprecated khi phù hợp, rồi loại bỏ field cũ trong một thay đổi breaking được lên kế hoạch. `@deprecated` không làm thay đổi nullability và cũng không khiến client cũ tự động chấp nhận null.

Với input nullable thành Non-Null, có thể thêm field input mới nullable trước, cập nhật client gửi giá trị, theo dõi usage, rồi siết thành Non-Null khi mọi client được hỗ trợ đã gửi giá trị. Nếu không thể chờ migration, tạo input type hoặc mutation mới để biểu diễn hợp đồng mới.

## Dùng default value có thể tránh bắt buộc input

GraphQL cho phép một argument hoặc input field Non-Null có default value. Khi đó client có thể bỏ qua field và server dùng default; explicit null vẫn bị từ chối:

```graphql
type Query {
  books(first: Int! = 20): [Book!]!
}

input SearchBooksInput {
  first: Int! = 20
}
```

Không nhầm `Int! = 20` với `Int!` không có default. Trường hợp đầu tiên không bắt buộc client phải gửi; trường hợp thứ hai bắt buộc phải có giá trị. Default value cần giữ đúng hành vi cũ để việc thêm argument mới không làm thay đổi kết quả của operation hiện tại.

Không dùng default giả tạo nếu nó che giấu lỗi dữ liệu hoặc tạo hành vi nghiệp vụ sai. Ví dụ tự thay `authorId` null bằng một tác giả mặc định có thể làm đơn hàng gắn nhầm chủ thể.

## Thiết kế resolver Spring for GraphQL theo nullability

SDL và kiểu trả về Java cần thống nhất. Ví dụ schema:

```graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  subtitle: String
}
```

Controller có thể trả null cho `book` khi không tìm thấy bản ghi vì field `Query.book` nullable. `title` phải luôn có giá trị; `subtitle` được phép không có:

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

Nếu schema đổi `book(id: ID!): Book!`, resolver không được trả null khi không tìm thấy. Có thể chọn ném exception nghiệp vụ và ánh xạ thành GraphQL error, hoặc thiết kế field nullable nếu “không tìm thấy” là kết quả bình thường của API. Không bắt exception rồi trả null cho field Non-Null vì điều đó sẽ tạo thêm execution error và null propagation.

Với field quan hệ, hãy xác định rõ ý nghĩa null. Ví dụ `Book.author: Author` có thể nullable nếu sách có thể chưa được gán tác giả; `Book.author: Author!` chỉ hợp lý khi mọi sách được phục vụ đều có tác giả và việc resolve luôn thành công theo hợp đồng. Nếu tác giả bị xóa, ẩn theo quyền hoặc dịch vụ tác giả tạm thời lỗi, Non-Null có thể làm mất cả object `Book` khỏi response.

### SDL Non-Null và Bean Validation

SDL `String!` và `@NotNull` trên DTO không thay thế nhau:

- SDL Non-Null là hợp đồng GraphQL. GraphQL từ chối input bị thiếu hoặc null trước khi gọi controller; với output, GraphQL kiểm tra giá trị DataFetcher trả về và áp dụng null propagation nếu vi phạm.
- `@NotNull` là validation ở tầng Java sau khi argument đã được bind. Nếu SDL vẫn khai báo `String`, client có thể gửi null theo schema, sau đó mới nhận validation error từ ứng dụng.
- `@NotBlank`, `@Size`, `@Positive` và các constraint khác kiểm tra nội dung mà GraphQL Non-Null không diễn tả được.

Khi thay đổi nullability, cập nhật SDL, resolver và DTO/validation policy đồng bộ. Không coi việc thêm `@NotNull` vào record là đã thay đổi GraphQL contract.

## Kiểm thử thay đổi nullability bằng GraphQlTester

Khi thay đổi schema, cần kiểm tra cả giá trị hợp lệ và trường hợp vi phạm guarantee. Với output nullable, test xác nhận null có thể được trả về mà không tạo execution error:

```java
@Test
void nullableSubtitleCanBeNull() {
    graphQlTester.document("""
            query {
              book(id: "book-10") {
                id
                subtitle
              }
            }
            """)
            .execute()
            .path("book.subtitle")
            .valueIsNull()
            .path("book.id")
            .entity(String.class)
            .isEqualTo("book-10");
}
```

Với field Non-Null, cố tình tạo fixture khiến resolver trả null để xác minh GraphQL trả error và null lan tới đúng parent nullable:

```java
@Test
void nonNullAuthorFailureNullsBookParent() {
    graphQlTester.document("""
            query {
              book(id: "book-without-author") {
                id
                author {
                  name
                }
              }
            }
            """)
            .execute()
            .errors()
            .expect(error -> error.getPath().contains("author"))
            .verify()
            .path("book")
            .valueIsNull();
}
```

Test giả định `Book.author` là `Author!` và `Query.book` là `Book` nullable. Nếu parent cũng là Non-Null, null sẽ lan xa hơn; điều chỉnh assertion theo đúng cấu trúc schema.

Với input Non-Null, kiểm tra cả trường hợp bị bỏ qua và explicit null:

```java
@Test
void requiredAuthorIdCannotBeOmitted() {
    graphQlTester.document("""
            mutation {
              createBook(input: { title: "Spring GraphQL" }) {
                id
              }
            }
            """)
            .execute()
            .errors()
            .expect(error -> error.getMessage().contains("authorId"))
            .verify();
}
```

Explicit null cũng bị từ chối:

```java
@Test
void requiredAuthorIdCannotBeNull() {
    graphQlTester.document("""
            mutation CreateBook($authorId: ID!) {
              createBook(input: { title: "Spring GraphQL", authorId: $authorId }) {
                id
              }
            }
            """)
            .variable("authorId", null)
            .execute()
            .errors()
            .expect(error -> error.getMessage().contains("authorId"))
            .verify();
}
```

Khi chạy schema check trong CI, so sánh schema hiện tại với schema đã publish và phân tích operation thực tế. Với Apollo GraphOS, build checks xác minh schema compose hợp lệ; operations checks so sánh các operation đã quan sát để phát hiện client có thể bị ảnh hưởng. Schema check hỗ trợ quyết định, nhưng không thay thế test resolver và kiểm tra dữ liệu production.

## Checklist trước khi đổi `!`

- Xác định đây là output field, field argument hay input object field.
- Với list, xác định dấu `!` đang áp dụng cho list wrapper hay item type.
- Xác định semantics của null: không tồn tại, chưa có, không được phép xem hay lỗi hệ thống.
- Kiểm tra resolver, service, database, downstream và authorization có thể trả null hay không.
- Kiểm tra dữ liệu cũ và migration/backfill.
- Xác định client generated types có thể bị ảnh hưởng như thế nào.
- Phân biệt omitted với explicit null đối với input update/patch.
- Kiểm tra default value; Non-Null có default vẫn có thể được bỏ qua.
- Viết test cho null, empty string, empty list, missing input và explicit null.
- Kiểm tra error path và null propagation với field Non-Null.
- Chạy schema diff/operation checks và theo dõi usage trước khi loại bỏ hợp đồng cũ.
- Triển khai resolver/data behavior đồng bộ với schema để tránh thời gian schema và runtime không khớp.

## Ghi nhớ

GraphQL mặc định nullable. `!` là cam kết mạnh của server đối với output và yêu cầu mạnh hơn đối với input. Với list, `[T]`, `[T]!`, `[T!]` và `[T!]!` khác nhau ở nullability của list và từng item; empty list vẫn hợp lệ ở mọi dạng.

Output nullable thành Non-Null thường là thay đổi tương thích nếu resolver thật sự luôn có giá trị; output Non-Null thành nullable là breaking vì client có thể nhận null. Input nullable thành Non-Null là breaking vì client có thể bỏ qua hoặc gửi null; input Non-Null thành nullable thường là nới lỏng nhưng cần định nghĩa hành vi mới. Khi Non-Null bị vi phạm, GraphQL tạo error và null lan lên parent nullable gần nhất. Hãy đo dữ liệu, sửa resolver, kiểm thử null propagation và migrate client theo chiến lược expand-contract trước khi thay đổi hợp đồng.

## Tài liệu tham khảo

- [GraphQL Specification — Type System: Non-Null and List](https://spec.graphql.org/September2026/#sec-Non-Null)
- [GraphQL Specification — Handling Execution Errors](https://spec.graphql.org/September2026/#sec-Handling-Field-Errors)
- [GraphQL.org — Schema and Type Modifiers](https://graphql.org/learn/schema/)
- [GraphQL.org — Schema Design: Nullability](https://graphql.org/learn/schema-design/)
- [GraphQL.org — Schema Change Management](https://graphql.org/learn/governance-versioning/)
- [Apollo GraphOS — Schema Checks](https://www.apollographql.com/docs/graphos/platform/schema-management/checks)
