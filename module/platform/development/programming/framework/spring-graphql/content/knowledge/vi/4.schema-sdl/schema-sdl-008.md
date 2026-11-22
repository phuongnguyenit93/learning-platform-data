# List type trong GraphQL SDL

GraphQL List type biểu diễn một danh sách các giá trị cùng kiểu. Trong Schema Definition Language (SDL), ta đặt kiểu phần tử trong cặp dấu ngoặc vuông, ví dụ `[Book]` hoặc `[String]`. List type thường được dùng để trả về nhiều bản ghi từ query, biểu diễn các thuộc tính có nhiều giá trị, hoặc nhận một tập điều kiện từ client.

Trong Spring for GraphQL, List type được khai báo trong schema như các kiểu GraphQL khác. Resolver Java thường trả về `List<T>` hoặc một `Collection<T>` tương ứng. Muốn thiết kế đúng, cần hiểu cả hai lớp: danh sách có thể `null` hay không và từng phần tử trong danh sách có thể `null` hay không.

## 1. Cú pháp List type cơ bản

Một kiểu danh sách có dạng `[Type]`, trong đó `Type` là kiểu của từng phần tử:

```graphql
type Query {
    bookTitles: [String]
    books: [Book]
}

type Book {
    id: ID!
    title: String!
}
```

`bookTitles` trả về danh sách chuỗi; `books` trả về danh sách các object `Book`. Mỗi phần tử trong danh sách có cùng kiểu GraphQL, nhưng giá trị của các phần tử có thể khác nhau.

List type có thể dùng với scalar, enum, object, interface hoặc union ở vị trí output. Ở vị trí input, phần tử phải là kiểu được phép nhận đầu vào như scalar, enum hoặc input object. Ví dụ, không thể khai báo một argument có kiểu `[Book]` nếu `Book` là object type; hãy tạo `input BookFilter` nếu cần nhận dữ liệu có cấu trúc.

GraphQL list giữ thứ tự phần tử. Danh sách cũng có thể chứa giá trị trùng lặp. Vì vậy, nếu thứ tự và số lần xuất hiện có ý nghĩa với API, kiểu Java `List<T>` thường thể hiện hợp đồng này rõ hơn `Set<T>`.

## 2. Kết hợp List type với Non-Null

Dấu `!` đặt sau một kiểu có nghĩa là giá trị tại vị trí đó không được `null`. Với danh sách, có hai vị trí độc lập để đặt `!`:

- Sau kiểu phần tử, bên trong dấu `[]`: quy định từng phần tử có được `null` hay không.
- Sau dấu `]`: quy định chính danh sách có được `null` hay không.

Bốn cách khai báo phổ biến:

| SDL | Danh sách có thể `null`? | Phần tử có thể `null`? | Ý nghĩa |
| --- | --- | --- | --- |
| `[Book]` | Có | Có | Có thể không có danh sách; nếu có, từng phần tử vẫn có thể null. |
| `[Book]!` | Không | Có | Luôn trả về một danh sách, nhưng danh sách có thể chứa phần tử null. |
| `[Book!]` | Có | Không | Danh sách có thể null; nếu có danh sách thì mọi phần tử đều phải có giá trị. |
| `[Book!]!` | Không | Không | Luôn trả về danh sách và mọi phần tử đều phải có giá trị. |

Ví dụ:

```graphql
type Query {
    allBooks: [Book!]!
    optionalRecommendations: [Book!]
    booksWithOptionalEntries: [Book]!
}
```

`allBooks: [Book!]!` là hợp đồng chặt chẽ: resolver luôn phải trả về một danh sách khác null và không có phần tử null. Khi chưa có sách phù hợp, trả về danh sách rỗng `[]` là hợp lệ. `optionalRecommendations: [Book!]` cho phép toàn bộ field không có giá trị (`null`), nhưng nếu trả về danh sách thì từng sách phải khác null.

`null` và `[]` mang ý nghĩa khác nhau. `null` biểu thị field không có giá trị theo hợp đồng của API; `[]` biểu thị đã có kết quả danh sách nhưng không có phần tử nào. Với field khai báo non-null, resolver phải trả về một giá trị thực, kể cả khi danh sách không có phần tử.

## 3. Nullability và cơ chế lan truyền lỗi

GraphQL thực thi ràng buộc Non-Null khi hoàn tất giá trị của từng field. Nếu resolver trả về `null` cho field non-null, hoặc một phần tử `null` xuất hiện ở vị trí có kiểu phần tử non-null, GraphQL tạo execution error và lan truyền giá trị null lên cấp cha gần nhất có thể nhận null.

Ví dụ, với khai báo:

```graphql
type Query {
    books: [Book!]!
}
```

nếu một phần tử trong danh sách `books` là `null`, toàn bộ danh sách không thể được hoàn tất vì phần tử có kiểu `Book!`. Field `books` cũng không được null vì có `!` ở ngoài danh sách, do đó giá trị null tiếp tục lan truyền lên cấp cha. Ở trường hợp field nằm trực tiếp trên root `Query`, kết quả `data` có thể trở thành `null`.

Nếu khai báo là `[Book!]` (danh sách nullable), lỗi do phần tử null vẫn làm danh sách trở thành null, nhưng lỗi không nhất thiết làm hỏng các field khác của object cha. Đây là lý do cần chọn nullability theo ý nghĩa nghiệp vụ và mức độ ảnh hưởng mà một lỗi phần tử có thể gây ra.

Khi thiết kế schema, hãy tự trả lời hai câu hỏi cho mỗi field danh sách: không có danh sách có phải là một trạng thái hợp lệ không, và một phần tử không có giá trị có phải là trạng thái hợp lệ không? Đừng thêm `!` chỉ để schema trông chặt chẽ; resolver và dữ liệu thực tế phải đáp ứng được hợp đồng đó.

## 4. Dùng List type cho Query và field lồng nhau

Ví dụ một API trả về danh sách sách:

```graphql
type Query {
    books: [Book!]!
    booksByAuthor(authorId: ID!): [Book!]!
}

type Book {
    id: ID!
    title: String!
    tags: [String!]!
}
```

`books` và `booksByAuthor` đều trả về danh sách `Book`. Field `tags` là một danh sách chuỗi nằm trong mỗi object `Book`. Khi client yêu cầu:

```graphql
query {
    booksByAuthor(authorId: "author-42") {
        id
        title
        tags
    }
}
```

GraphQL trả về mảng JSON cho mỗi field list:

```json
{
  "data": {
    "booksByAuthor": [
      {
        "id": "book-1",
        "title": "GraphQL cơ bản",
        "tags": ["backend", "api"]
      },
      {
        "id": "book-2",
        "title": "Thiết kế schema",
        "tags": []
      }
    ]
  }
}
```

Danh sách `tags` rỗng ở sách thứ hai vẫn hợp lệ với `[String!]!`: danh sách tồn tại và không có phần tử nào vi phạm kiểu. Nếu một field `tags` trả về `null`, hợp đồng non-null sẽ bị vi phạm.

## 5. Khai báo List type trong input

List type cũng có thể xuất hiện trong argument của field hoặc trong input object. Ví dụ client muốn tìm nhiều sách theo danh sách ID và tag:

```graphql
input BookSearchInput {
    ids: [ID!]!
    tags: [String!]
}

type Query {
    searchBooks(filter: BookSearchInput!): [Book!]!
}
```

Ở đây, `ids` bắt buộc phải có một danh sách và từng ID không được null. `tags` có thể không được truyền hoặc có giá trị null; nếu có danh sách thì các tag bên trong không được null. Nếu nghiệp vụ yêu cầu `tags` luôn có mặt, có thể đổi thành `[String!]!`.

Client gửi biến như sau:

```graphql
query SearchBooks($filter: BookSearchInput!) {
    searchBooks(filter: $filter) {
        id
        title
    }
}
```

```json
{
  "filter": {
    "ids": ["book-1", "book-2"],
    "tags": ["backend", "spring"]
  }
}
```

GraphQL hỗ trợ list input coercion: tại vị trí mong đợi một list, một giá trị đơn có thể được chuyển thành danh sách một phần tử. Dù vậy, client nên gửi mảng một cách nhất quán để request dễ đọc và tránh nhầm lẫn khi mở rộng từ một giá trị sang nhiều giá trị.

Giá trị mặc định của input list có thể được khai báo bằng literal danh sách trong SDL:

```graphql
type Query {
    booksByStatus(statuses: [BookStatus!] = [PUBLISHED]): [Book!]!
}

enum BookStatus {
    DRAFT
    PUBLISHED
    ARCHIVED
}
```

Khi client bỏ qua `statuses`, GraphQL sử dụng giá trị mặc định `[PUBLISHED]`. Nếu client truyền giá trị rõ ràng, giá trị được truyền sẽ được dùng theo quy tắc coercion của GraphQL.

## 6. Ánh xạ List type sang Java với Spring for GraphQL

Spring for GraphQL dùng GraphQL Java để thực thi schema. Với field có kiểu danh sách, resolver có thể trả về `List<T>`, `Collection<T>` hoặc một kiểu giá trị có thể được GraphQL Java xử lý như danh sách. Trong ứng dụng Spring, `List<T>` thường là lựa chọn đơn giản và dễ hiểu nhất.

Ví dụ resolver cho query `books`:

```java
import java.util.List;

import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> books() {
        return bookService.findAll();
    }
}
```

Giả sử `Book` là kiểu dữ liệu Java mà các field của nó có thể được ánh xạ với object type `Book` trong SDL. Tên method `books` khớp với field `books` của root type `Query`; `@QueryMapping` đăng ký method làm data fetcher cho field đó.

Để ánh xạ một field danh sách nằm trong object, có thể dùng `@SchemaMapping`:

```java
import java.util.List;

import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookFieldController {

    private final TagService tagService;

    public BookFieldController(TagService tagService) {
        this.tagService = tagService;
    }

    @SchemaMapping(typeName = "Book", field = "tags")
    public List<String> tags(Book book) {
        return tagService.findNamesByBookId(book.id());
    }
}
```

Method nhận object cha `Book` và trả về danh sách chuỗi tương ứng với field `tags`. Nếu tên method trùng tên field và tên lớp trùng GraphQL type, một số thuộc tính của `@SchemaMapping` có thể được suy ra theo quy ước; khai báo tường minh giúp ví dụ dễ theo dõi.

Với input object, có thể ánh xạ argument vào một Java record hoặc class có thuộc tính tương ứng:

```java
public record BookSearchInput(List<String> ids, List<String> tags) {}
```

```java
@QueryMapping
public List<Book> searchBooks(@Argument("filter") BookSearchInput filter) {
    return bookService.search(filter);
}
```

Tên và kiểu thuộc tính của Java input cần tương thích với các field của `BookSearchInput` trong SDL. Nếu schema dùng `ID`, ứng dụng có thể biểu diễn ID bằng `String` hoặc kiểu ID phù hợp với domain; hãy giữ cách ánh xạ nhất quán trong các resolver.

## 7. Quy tắc xử lý danh sách trong resolver

Khi schema khai báo `[Book!]!`, resolver phải bảo đảm hai điều kiện: không trả về `null` cho cả danh sách và không để phần tử null lọt vào kết quả. Ví dụ:

```java
@QueryMapping
public List<Book> books() {
    List<Book> result = bookService.findAll();
    return result == null ? List.of() : result;
}
```

Đoạn code trên minh họa cách bảo đảm danh sách ngoài cùng không null. Trong thiết kế service tốt, `findAll()` nên quy định rõ rằng không có kết quả thì trả về danh sách rỗng. Nếu dữ liệu nguồn có thể chứa phần tử null, cần xử lý nguyên nhân ở tầng domain hoặc service thay vì âm thầm trả dữ liệu vi phạm schema.

Một số nguyên tắc thực tế:

- Dùng `[]` khi truy vấn thành công nhưng không có phần tử phù hợp.
- Chỉ trả `null` nếu field được khai báo nullable và nghiệp vụ có trạng thái thực sự cần biểu diễn bằng null.
- Không trả phần tử null cho list có kiểu phần tử non-null.
- Giữ thứ tự kết quả ổn định nếu thứ tự có ý nghĩa với client; dùng `ORDER BY` hoặc sắp xếp có chủ đích ở tầng truy vấn.
- Không chuyển sang `Set` nếu API cần giữ phần tử trùng lặp hoặc thứ tự của nguồn dữ liệu.
- Kiểm soát kích thước danh sách và cung cấp pagination cho tập dữ liệu lớn.

GraphQL không tự đặt giới hạn số phần tử tối đa cho một list field. Nếu query có thể trả về hàng chục nghìn phần tử, server có thể tốn nhiều bộ nhớ và thời gian serialize. Hãy thiết kế pagination, giới hạn kích thước trang và kiểm soát độ sâu hoặc độ phức tạp query theo yêu cầu hệ thống.

## 8. List type và vấn đề N+1

Một field danh sách có thể làm lộ rõ vấn đề N+1 khi resolver truy vấn dữ liệu cho từng phần tử. Ví dụ, `books` trả về 100 sách và resolver `Book.tags` thực hiện một truy vấn riêng cho mỗi sách. Khi đó một request có thể tạo một truy vấn lấy sách và thêm 100 truy vấn lấy tag.

Với trường hợp này, có thể gom việc tải dữ liệu theo lô bằng `@BatchMapping` hoặc DataLoader. Cách triển khai cần trả kết quả tương ứng đúng với từng object cha và giữ hợp đồng kiểu trong SDL. List type chỉ mô tả hình dạng dữ liệu mà client nhận; nó không tự tối ưu số lần truy cập database.

Khi làm việc với list lồng nhau, hãy xem xét cả kích thước từng danh sách lẫn số lần resolver được gọi. Một query yêu cầu nhiều sách, mỗi sách có nhiều tác giả và nhiều tag có thể tạo ra lượng dữ liệu lớn ngay cả khi số HTTP request chỉ là một.

## 9. Kiểm thử field trả về danh sách

Kiểm thử nên xác nhận cả số phần tử, giá trị và hợp đồng nullability. Ví dụ với `GraphQlTester` đã được cấu hình trong test context:

```java
@Test
void booksReturnsAnOrderedList() {
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
        .entityList(BookView.class)
        .hasSize(2);
}
```

Ngoài số lượng, nên kiểm tra thứ tự nếu API cam kết thứ tự kết quả, kiểm tra `[]` khi không có dữ liệu, và kiểm tra lỗi khi resolver tạo ra giá trị vi phạm Non-Null. Với field nullable, kiểm thử riêng trường hợp `null` nếu đó là trạng thái hợp lệ theo nghiệp vụ.

Ví dụ một kiểm thử input list có thể gửi nhiều ID:

```java
@Test
void searchBooksAcceptsSeveralIds() {
    graphQlTester.document("""
            query Search($filter: BookSearchInput!) {
                searchBooks(filter: $filter) { id }
            }
            """)
        .variable("filter", java.util.Map.of("ids", List.of("book-1", "book-2")))
        .execute()
        .path("searchBooks")
        .entityList(BookIdView.class)
        .hasSize(2);
}
```

Các class `BookView` và `BookIdView` trong ví dụ là DTO test có thuộc tính phù hợp với selection set. Test cần thiết lập dữ liệu cố định để kết quả có thể dự đoán và lặp lại.

## 10. Danh sách lồng nhau

GraphQL cho phép một list chứa các list khác. Ví dụ:

```graphql
type Query {
    scoreMatrix: [[Int!]!]!
}
```

`[[Int!]!]!` có nghĩa danh sách ngoài không null, từng danh sách con không null và từng số nguyên không null. Một response hợp lệ có thể là:

```json
{
  "data": {
    "scoreMatrix": [
      [8, 9, 10],
      [7, 8, 9]
    ]
  }
}
```

Kiểu lồng nhau phù hợp với dữ liệu có cấu trúc dạng ma trận hoặc nhóm theo nhóm. Với dữ liệu nghiệp vụ phức tạp, cân nhắc dùng object type có tên rõ ràng thay vì list lồng nhau nhiều cấp; object giúp mỗi thành phần có ngữ nghĩa và field riêng, dễ mở rộng hơn.

## 11. Lỗi thường gặp khi sử dụng List type

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| Field khai báo `[Book!]!` nhưng trả về null | Resolver hoặc service trả null khi không có dữ liệu | Quy ước trả về danh sách rỗng hoặc sửa schema nếu null là trạng thái hợp lệ. |
| Toàn bộ field list thành null khi chỉ một phần tử lỗi | Phần tử vi phạm `Book!`; lỗi null lan truyền theo hợp đồng Non-Null | Xác minh dữ liệu từng phần tử và chọn nullability phù hợp. |
| Không truyền được object làm input list | Dùng object type ở vị trí input | Khai báo `input` type và dùng `[InputType]` nếu cần danh sách input object. |
| Thứ tự phần tử không ổn định | Truy vấn database không có `ORDER BY` hoặc dùng collection không giữ thứ tự | Sắp xếp kết quả theo tiêu chí API công bố. |
| Request hoặc response quá lớn | List không có giới hạn kích thước hoặc pagination | Thêm pagination và giới hạn kích thước trang. |
| Số truy vấn database tăng theo số phần tử | Resolver field con thực hiện truy vấn riêng cho từng object | Dùng `@BatchMapping`, DataLoader hoặc truy vấn lấy dữ liệu theo lô. |

## 12. Checklist thiết kế List type

1. Chọn đúng kiểu phần tử: scalar, enum, object hoặc input object theo vị trí sử dụng.
2. Quyết định độc lập việc danh sách và từng phần tử có được phép null hay không.
3. Dùng `[T!]!` khi API luôn phải trả về danh sách và mọi phần tử đều có giá trị; trả `[]` nếu không có kết quả.
4. Dùng Java `List<T>` hoặc collection phù hợp để ánh xạ resolver, bảo đảm thứ tự và nullability đúng hợp đồng SDL.
5. Dùng input object khi cần truyền một nhóm điều kiện có cấu trúc.
6. Thiết kế pagination và giới hạn kích thước cho danh sách lớn.
7. Kiểm tra nguy cơ N+1 khi các phần tử có field cần tải dữ liệu bổ sung.
8. Kiểm thử danh sách có dữ liệu, danh sách rỗng, thứ tự và các trường hợp null/error.

List type giúp GraphQL biểu diễn dữ liệu nhiều phần tử một cách nhất quán ở cả input và output. Khi kết hợp đúng với Non-Null, ánh xạ Java và chiến lược tải dữ liệu, schema sẽ mô tả rõ những gì client có thể nhận hoặc gửi, đồng thời giúp server phát hiện sớm các kết quả vi phạm hợp đồng API.
