# Schema documentation bằng mô tả

Một GraphQL schema cho biết API có những type, field, argument và kiểu trả về nào. Nhưng tên `Book.status: BookStatus!` chưa giải thích trạng thái nào có thể xuất hiện, khi nào một cuốn sách được xem là `ARCHIVED`, hay client nên làm gì khi gặp giá trị đó. Để biến schema thành một hợp đồng dễ hiểu, GraphQL SDL hỗ trợ **description** cho các thành phần của schema.

Description là chuỗi văn bản gắn trực tiếp với định nghĩa type, field, argument, enum value, input field, scalar, directive và các thành phần schema phù hợp khác. GraphQL đưa mô tả này vào introspection, nhờ đó công cụ như GraphiQL, IDE và tài liệu API có thể hiển thị nội dung mà không cần đọc mã Java của server.

Trong Spring for GraphQL, schema thường được khai báo bằng SDL trong `src/main/resources/graphql/`. Vì vậy, tài liệu API nên được viết ngay cạnh định nghĩa SDL mà nó giải thích. Bài học này trình bày cú pháp mô tả, cách truy vấn mô tả qua introspection, cách phân biệt description với comment và deprecation, cùng nguyên tắc viết tài liệu hữu ích cho client.

## 1. Description là một phần của GraphQL schema

GraphQL SDL cho phép đặt một string literal ngay trước định nghĩa cần mô tả. Ví dụ:

```graphql
"""
Thông tin công khai của một cuốn sách trong thư viện.
Các field trong type này được dùng cho màn hình danh sách và chi tiết.
"""
type Book {
  """Mã định danh ổn định của cuốn sách."""
  id: ID!

  """Tiêu đề hiển thị cho người đọc."""
  title: String!

  """Năm phát hành; có thể không có với tài liệu chưa xuất bản."""
  publishedYear: Int
}
```

Chuỗi mô tả đứng ngay trước định nghĩa mà nó bổ nghĩa. Trong ví dụ, description đầu tiên thuộc về `Book`; các description tiếp theo thuộc về từng field. Khi schema được parse, GraphQL giữ lại những mô tả này trong metadata của schema.

Description không làm thay đổi cách resolver chạy và không thay đổi kiểu dữ liệu. Nó bổ sung ngữ nghĩa cho hợp đồng API để người dùng biết field đại diện cho điều gì, có thể nhận giá trị nào và nên được sử dụng ra sao.

## 2. Viết description một dòng và nhiều dòng

GraphQL hỗ trợ hai dạng string literal thường dùng cho description.

### Chuỗi một dòng

Chuỗi đặt trong dấu nháy kép phù hợp với mô tả ngắn:

```graphql
type Author {
  "Tên hiển thị của tác giả."
  name: String!
}
```

Nếu nội dung có dấu nháy kép hoặc ký tự đặc biệt, hãy escape theo cú pháp string của GraphQL. Không dùng dấu nháy đơn để thay thế dấu nháy kép.

### Block string nhiều dòng

Block string được bao bởi ba dấu nháy kép. Dạng này phù hợp với mô tả có nhiều câu, ví dụ giải thích ý nghĩa nghiệp vụ hoặc điều kiện sử dụng:

```graphql
"""
Một cuốn sách trong danh mục thư viện.

`Book` đại diện cho tài liệu có thể được tìm kiếm và hiển thị.
Field `author` có thể không tồn tại nếu dữ liệu tác giả chưa được liên kết.
"""
type Book {
  id: ID!
  title: String!
  author: Author
}
```

GraphQL chuẩn hóa indentation của block string để phần thụt lề phục vụ định dạng SDL không trở thành nội dung thừa trong description. Dù vậy, nên viết block string gọn, có dòng trống khi chuyển ý và tránh chèn khoảng trắng không cần thiết ở đầu hoặc cuối.

Có thể dùng Markdown nhẹ trong nội dung description nếu công cụ hiển thị hỗ trợ, ví dụ tên field đặt trong backticks hoặc danh sách ngắn. Tuy nhiên, giá trị chuẩn mà introspection trả về vẫn là string; không phải mọi client đều render Markdown giống nhau. Hãy bảo đảm mô tả vẫn dễ hiểu khi hiển thị như văn bản thuần.

## 3. Mô tả type, field và argument

Một description hữu ích trả lời câu hỏi mà client cần biết tại đúng vị trí sử dụng. Nên mô tả type ở cấp khái quát, field ở cấp ý nghĩa dữ liệu và argument ở cấp cách truyền tham số.

```graphql
"""
Thông tin tác giả có sách được lưu trong thư viện.
"""
type Author {
  "Mã định danh của tác giả."
  id: ID!

  "Tên được dùng để hiển thị và tìm kiếm."
  name: String!

  """
Các sách của tác giả.

Danh sách được phân trang theo `first`; kết quả không bao gồm sách đã xóa.
"""
  books(
    "Số sách tối đa muốn nhận trong một lần gọi; mặc định là 10."
    first: Int = 10
  ): [Book!]!
}
```

Description của argument nằm ngay trước argument bên trong dấu ngoặc của field. Điều này đặc biệt hữu ích khi một field có nhiều tham số như filter, sort, pagination hoặc cờ tùy chọn.

Khi thiết kế mô tả cho field có argument, hãy giải thích:

- Đơn vị của giá trị, ví dụ giây, phút, đồng tiền hoặc số phần tử.
- Miền giá trị hợp lệ và giá trị mặc định.
- Ý nghĩa của việc bỏ qua argument hoặc truyền `null`, nếu khác nhau.
- Quy tắc phân trang, sắp xếp hoặc lọc mà client cần biết.

Ví dụ về filter:

```graphql
type Query {
  """
Tìm sách theo tiêu chí tùy chọn.

Các tiêu chí được kết hợp bằng phép AND. Nếu không truyền filter,
API trả về danh sách sách theo thứ tự cập nhật mới nhất.
"""
  books(
    "Các điều kiện lọc sách. Có thể bỏ qua để lấy danh sách mặc định."
    filter: BookFilter
  ): [Book!]!
}

input BookFilter {
  "Từ khóa tìm trong tiêu đề, không phân biệt chữ hoa và chữ thường."
  keyword: String

  "Chỉ lấy sách thuộc trạng thái được chỉ định."
  status: BookStatus
}
```

Mô tả cần khớp hành vi thật của resolver. Nếu description nói filter được kết hợp bằng AND nhưng implementation dùng OR, tài liệu sẽ khiến client tích hợp sai dù schema vẫn validate thành công.

## 4. Mô tả input object và input field

Input object thường được dùng trong mutation hoặc filter. Mô tả ở cấp input type giúp client hiểu mục đích của nhóm dữ liệu; mô tả từng input field giải thích yêu cầu và quy tắc của từng giá trị.

```graphql
"""
Dữ liệu cần thiết để tạo một cuốn sách.

Server tự sinh `id` và thời điểm tạo. Client không gửi các giá trị này.
"""
input CreateBookInput {
  "Tiêu đề sách; không được để trống sau khi loại bỏ khoảng trắng."
  title: String!

  "Mã tác giả đã tồn tại trong thư viện."
  authorId: ID!

  "Trạng thái ban đầu; mặc định là DRAFT nếu không truyền."
  status: BookStatus = DRAFT
}

type Mutation {
  "Tạo sách mới và trả về bản ghi sau khi lưu."
  createBook(input: CreateBookInput!): Book!
}
```

Mô tả `title` nói rõ một quy tắc nghiệp vụ mà kiểu `String!` không thể biểu đạt: chuỗi không được để trống sau khi trim. Non-null chỉ ngăn `null`; nó không tự ngăn chuỗi rỗng hoặc chuỗi chỉ có dấu cách. Server vẫn phải validate input trong code.

Tương tự, `authorId: ID!` bảo đảm client phải truyền ID khác `null`, nhưng không bảo đảm tác giả đó tồn tại hoặc người gọi có quyền gắn tác giả đó vào sách. Description nên giải thích ý nghĩa và validation quan trọng, còn server chịu trách nhiệm kiểm tra thực tế.

## 5. Mô tả enum, scalar, interface và directive

### Enum và từng enum value

Enum mô tả một miền giá trị hữu hạn. Mỗi giá trị nên có description nếu ý nghĩa nghiệp vụ không hiển nhiên:

```graphql
"Trạng thái vòng đời của một cuốn sách."
enum BookStatus {
  "Sách đang được biên tập và chưa hiển thị công khai."
  DRAFT

  "Sách đã được phát hành và có thể được tìm kiếm."
  PUBLISHED

  "Sách đã ngừng lưu hành nhưng vẫn còn trong lịch sử."
  ARCHIVED
}
```

Mô tả enum giải thích miền giá trị tổng thể; mô tả từng enum value giải thích khác biệt về hành vi. Điều này giúp client xây dựng bộ lọc, badge trạng thái hoặc luồng thao tác phù hợp.

### Scalar

Custom scalar nên có mô tả về định dạng, đơn vị, múi giờ và quy tắc parse/serialize:

```graphql
"""
Thời điểm theo chuẩn ISO-8601, có thông tin múi giờ.

Ví dụ: `2026-11-20T09:30:00+07:00`.
"""
scalar DateTime
```

Chỉ ghi ví dụ nếu định dạng đó thực sự được custom scalar chấp nhận. Description không đăng ký scalar runtime và không thay thế coercing implementation.

### Interface và union

Interface có thể mô tả hợp đồng chung của các type triển khai nó. Field của interface cũng có thể có description:

```graphql
"Một nội dung có thể xuất hiện trong kết quả tìm kiếm."
interface SearchResult {
  "Mã định danh của kết quả."
  id: ID!

  "Tiêu đề dùng để hiển thị trong danh sách kết quả."
  title: String!
}

"Kết quả tìm kiếm là sách hoặc tác giả."
union SearchItem = Book | Author
```

Với union, mô tả ở cấp union giúp client hiểu các loại object có thể xuất hiện. Các object type thành viên vẫn cần mô tả riêng để giải thích dữ liệu cụ thể.

### Directive tùy chỉnh

Directive có thể được mô tả cùng argument của nó:

```graphql
"Đánh dấu field chỉ dành cho client nội bộ."
directive @internalOnly(
  "Lý do field bị giới hạn truy cập."
  reason: String
) on FIELD_DEFINITION
```

Description giải thích mục đích directive, nhưng không tự tạo hành vi bảo mật. Muốn giới hạn quyền truy cập, server cần triển khai logic tương ứng bằng wiring, instrumentation, interceptor hoặc cơ chế authorization phù hợp.

## 6. Phân biệt description với comment trong SDL

GraphQL SDL cũng hỗ trợ comment bắt đầu bằng `#`. Comment hữu ích để ghi chú cho người đang đọc file schema, nhưng comment không phải description của schema element và không được trả về qua introspection.

```graphql
# Đây là comment của file SDL. Tooling introspection không nhận nội dung này.
type Book {
  "Mô tả này gắn với field và có thể được introspection trả về."
  title: String!
}
```

| Tiêu chí | Comment `#` | Description string |
| --- | --- | --- |
| Mục đích | Ghi chú cho người đọc file SDL | Tài liệu của API schema |
| Cú pháp | `# nội dung` | String literal đặt trước định nghĩa |
| Gắn với type/field | Không | Có |
| Xuất hiện qua introspection | Không | Có |
| Hiển thị trong tooling schema | Thường không | Có, nếu tooling hỗ trợ |

Không nên dùng comment thay cho description nếu nội dung cần được client, GraphiQL hoặc công cụ sinh tài liệu truy cập. Ngược lại, comment vẫn phù hợp cho ghi chú triển khai nội bộ không thuộc hợp đồng API.

## 7. Truy vấn description bằng introspection

GraphQL introspection cho phép client hỏi schema về type, field, argument, enum value và description của chúng. Các trường `description` trên introspection type trả về nội dung đã khai báo trong SDL.

Ví dụ truy vấn mô tả type `Book` và các field:

```graphql
query BookDocumentation {
  __type(name: "Book") {
    name
    description
    fields {
      name
      description
      args {
        name
        description
      }
    }
  }
}
```

Response rút gọn:

```json
{
  "data": {
    "__type": {
      "name": "Book",
      "description": "Thông tin công khai của một cuốn sách trong thư viện. Các field trong type này được dùng cho màn hình danh sách và chi tiết.",
      "fields": [
        {
          "name": "id",
          "description": "Mã định danh ổn định của cuốn sách.",
          "args": []
        },
        {
          "name": "title",
          "description": "Tiêu đề hiển thị cho người đọc.",
          "args": []
        }
      ]
    }
  }
}
```

Để xem mô tả và trạng thái deprecation của enum value:

```graphql
query BookStatusDocumentation {
  __type(name: "BookStatus") {
    name
    description
    enumValues(includeDeprecated: true) {
      name
      description
      isDeprecated
      deprecationReason
    }
  }
}
```

Introspection hữu ích cho tooling và kiểm tra tài liệu. Tuy nhiên, server có thể cấu hình chính sách hạn chế introspection trong môi trường production. Việc tắt introspection không xóa description khỏi schema đã nạp; nó chỉ làm client không thể truy vấn metadata qua cơ chế introspection tại endpoint đó.

## 8. Description khác với deprecation

Description giải thích ý nghĩa và cách sử dụng hiện tại của một thành phần. Deprecation thông báo thành phần đó đã cũ và khuyến nghị client chuyển sang cách thay thế.

GraphQL có directive chuẩn `@deprecated`, có thể áp dụng cho field và enum value:

```graphql
type Book {
  "Mã sách hiện tại."
  id: ID!

  "Mã cũ, giữ lại để tương thích với client phiên bản trước."
  legacyCode: String @deprecated(reason: "Use `id` instead.")
}

enum BookFormat {
  PAPERBACK
  HARDCOVER
  PRINTED @deprecated(reason: "Use PAPERBACK or HARDCOVER.")
}
```

Trong introspection, client có thể đọc `isDeprecated` và `deprecationReason`. Description và deprecation reason có mục đích khác nhau:

- Description mô tả field đang làm gì và dữ liệu có ý nghĩa ra sao.
- `@deprecated` báo rằng client nên ngừng sử dụng field hoặc enum value.
- `reason` giải thích vì sao bị deprecated hoặc gợi ý field thay thế.

Không dùng deprecation để thay cho việc xóa field ngay lập tức. Một lộ trình an toàn thường gồm công bố field mới, đánh dấu field cũ deprecated, cập nhật client, theo dõi mức sử dụng và chỉ loại bỏ field cũ theo chính sách versioning/compatibility của API.

## 9. Description được sử dụng trong Spring for GraphQL như thế nào?

Spring for GraphQL thường dùng schema-first: Spring Boot nạp các file `.graphqls` hoặc `.gqls`, xây dựng `GraphQlSource`, rồi kết nối schema với resolver trong controller. Description được parse cùng SDL và giữ trong schema runtime.

Ví dụ file `src/main/resources/graphql/book.graphqls`:

```graphql
"Thông tin sách hiển thị trong thư viện."
type Book {
  "Mã sách do server quản lý."
  id: ID!

  "Tiêu đề sách."
  title: String!
}

type Query {
  "Tìm một sách theo ID. Trả về null nếu không tìm thấy."
  book(id: ID!): Book
}
```

Resolver Java chỉ cần ánh xạ field theo tên và cung cấp dữ liệu:

```java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id);
    }
}
```

Không cần thêm annotation vào method Java để description trong SDL xuất hiện. Description thuộc về schema; `@QueryMapping` chỉ kết nối field `Query.book` với method Java. Nếu thay đổi description nhưng giữ nguyên tên và kiểu field, logic resolver không cần thay đổi.

Có thể kiểm tra mô tả qua `GraphQlTester` bằng introspection:

```java
graphQlTester.document("""
        query {
            __type(name: "Book") {
                name
                description
                fields {
                    name
                    description
                }
            }
        }
        """)
    .execute()
    .path("__type.description")
    .entity(String.class)
    .isEqualTo("Thông tin sách hiển thị trong thư viện.");
```

Test này xác nhận description đã được nạp vào schema runtime, thay vì chỉ xác nhận file SDL có chứa chuỗi mô tả. Nếu ứng dụng giới hạn introspection, hãy kiểm tra schema ở test context phù hợp hoặc dùng cơ chế kiểm thử nội bộ được phép.

## 10. Nguyên tắc viết description có chất lượng

Một description tốt giúp client sử dụng API đúng mà không phải đọc source code server hoặc hỏi nhóm backend về từng field.

### Viết theo góc nhìn client

Mô tả ý nghĩa của dữ liệu đối với client, không mô tả chi tiết triển khai nội bộ. Ví dụ:

| Mô tả yếu | Mô tả tốt hơn |
| --- | --- |
| `Lấy sách.` | `Tìm một sách theo ID. Trả về null nếu không tìm thấy.` |
| `Tên tác giả.` | `Tên hiển thị của tác giả, dùng trong thẻ sách và kết quả tìm kiếm.` |
| `Số lượng.` | `Số sách tối đa trả về trong một trang; giá trị mặc định là 20.` |
| `Trạng thái.` | `Trạng thái vòng đời của sách: DRAFT, PUBLISHED hoặc ARCHIVED.` |

### Ghi rõ giới hạn và quy tắc

Nếu field có quy tắc đặc biệt, hãy nói rõ. Ví dụ `price: Decimal!` chưa cho biết đơn vị tiền, có bao gồm thuế hay không, hoặc giá trị được làm tròn như thế nào. Nếu các quy tắc này ảnh hưởng đến client, hãy ghi chúng trong description của field hoặc type tương ứng.

### Không lặp lại thông tin mà kiểu đã thể hiện

Với `id: ID!`, mô tả `ID của sách` có thể đủ. Không cần viết dài dòng chỉ để nhắc rằng field là bắt buộc; dấu `!` đã thể hiện điều đó. Hãy dùng phần mô tả để giải thích ý nghĩa nghiệp vụ, format hoặc hành vi mà kiểu không thể biểu đạt.

### Giữ mô tả nhất quán với resolver

Nếu description nói một danh sách được sắp xếp theo thời gian giảm dần, resolver phải thực hiện đúng thứ tự đó. Nếu description nói `null` nghĩa là không tìm thấy, không nên dùng cùng giá trị `null` cho trường hợp người dùng không đủ quyền nếu client cần phân biệt hai tình huống. Tài liệu sai có thể nguy hiểm hơn thiếu tài liệu vì client sẽ dựa vào nó để xây dựng hành vi.

### Dùng thuật ngữ nhất quán

Chọn một cách gọi cho khái niệm nghiệp vụ và dùng xuyên suốt schema. Ví dụ, nếu API dùng `author` cho tác giả, không nên lúc khác gọi cùng khái niệm là `writer` chỉ vì tên đó nghe tự nhiên hơn. Mô tả có thể giải thích từ đồng nghĩa khi cần, nhưng tên type và field cần ổn định.

## 11. Checklist khi review schema documentation

Trước khi hoàn tất một thay đổi SDL, hãy kiểm tra:

- Type quan trọng có description giải thích vai trò trong API.
- Field có tên không hiển nhiên được mô tả rõ ý nghĩa và đơn vị.
- Argument có quy tắc mặc định, miền giá trị hoặc cách phân trang được giải thích.
- Input field nói rõ điều kiện validation nghiệp vụ quan trọng.
- Enum value có mô tả đủ để client phân biệt trạng thái.
- Custom scalar ghi rõ format, múi giờ, đơn vị và ví dụ hợp lệ.
- Field/type cũ được đánh dấu `@deprecated` kèm lý do và gợi ý thay thế.
- Description không mâu thuẫn với nullability, default value hoặc hành vi resolver.
- Nội dung cần hiển thị cho client được viết dưới dạng description, không chỉ là comment `#`.
- Introspection/tooling của môi trường kiểm thử hiển thị đúng mô tả mong đợi.

## 12. Bài tập thực hành

Hãy bổ sung tài liệu cho schema của một thư viện:

1. Viết description cho `Book`, `Author`, `BookStatus` và `CreateBookInput`.
2. Mô tả các field `Book.id`, `Book.title`, `Book.author` và argument `Query.books(first:)`.
3. Mô tả từng enum value của `BookStatus` để client biết khi nào một sách ở trạng thái đó.
4. Dùng `@deprecated` cho field `Book.oldTitle` và nêu field thay thế trong reason.
5. Viết introspection query để đọc description của `Book`, field `title` và enum values.
6. Viết test `GraphQlTester` xác nhận description của type `Book` đúng như SDL.

Ví dụ phần schema có thể bắt đầu như sau:

```graphql
"""Thông tin sách được quản lý trong thư viện."""
type Book {
  """Mã định danh ổn định của sách."""
  id: ID!

  """Tiêu đề chính thức dùng để hiển thị."""
  title: String!

  """Tiêu đề cũ, giữ lại để tương thích với client trước đây."""
  oldTitle: String @deprecated(reason: "Use `title` instead.")
}
```

Khi hoàn thành, hãy mở GraphiQL hoặc chạy introspection query và xác nhận các mô tả xuất hiện trong schema runtime. Mục tiêu là để một client mới có thể hiểu ý nghĩa, giới hạn và cách sử dụng API thông qua schema mà không cần đọc implementation Java.
