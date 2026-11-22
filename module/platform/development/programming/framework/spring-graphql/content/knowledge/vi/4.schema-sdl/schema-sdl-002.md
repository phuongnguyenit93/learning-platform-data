# type Query

Trong GraphQL SDL, **type Query** khai báo root object type cho các thao tác đọc dữ liệu của API. Những field được định nghĩa bên trong type này là các điểm bắt đầu mà client có thể gọi khi gửi một query operation. Mỗi field mô tả tên thao tác, các argument đầu vào và kiểu dữ liệu trả về.

Với Spring for GraphQL, schema SDL là hợp đồng của API, còn các method Java được ánh xạ vào field của Query bằng annotation như `@QueryMapping`. Hiểu rõ cách thiết kế type Query giúp API dễ khám phá, có kiểu dữ liệu rõ ràng, dễ kiểm thử và kiểm soát được chi phí truy vấn phía server.

## 1. Vai trò của root type Query

Một schema GraphQL có ba loại root operation:

- **Query** dùng để đọc dữ liệu.
- **Mutation** dùng để thay đổi trạng thái dữ liệu.
- **Subscription** dùng để nhận các sự kiện hoặc kết quả được phát ra theo thời gian.

Trong SDL, root query type thường được đặt tên là Query:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

Ở đây:

- `type` khai báo một object type.
- `Query` là tên object type đóng vai trò root cho query operation.
- `book` là field mà client có thể yêu cầu.
- `id: ID!` là argument bắt buộc của field.
- `Book` là kiểu kết quả. Vì không có dấu `!`, field có thể trả về `null`.

Khi không khai báo khối `schema`, GraphQL dùng object type tên `Query` làm query root. Vì vậy, với cách đặt tên thông dụng này, không cần khai báo riêng khối `schema`.

Tên `Query` là quy ước mặc định của GraphQL, không phải từ khóa bắt buộc trong mọi schema. Nếu muốn dùng tên khác, phải khai báo root operation rõ ràng:

~~~graphql
schema {
    query: CatalogQuery
}

type CatalogQuery {
    book(id: ID!): Book
}
~~~

Root query type phải là một object type. Nó không thể là scalar, enum, input object hoặc list. Object type cũng cần có ít nhất một field hợp lệ để client có thể truy vấn.

### Phân biệt type Query và query operation

Hai khái niệm này có liên quan nhưng thuộc hai phần khác nhau của GraphQL:

| Khái niệm | Ý nghĩa |
| --- | --- |
| `type Query` | Định nghĩa các field mà server cung cấp làm điểm bắt đầu cho thao tác đọc dữ liệu. |
| `query` | Từ khóa dùng trong operation document do client gửi lên để yêu cầu thực thi thao tác đọc. |

Ví dụ schema:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

Ví dụ operation của client:

~~~graphql
query BookDetail($id: ID!) {
    book(id: $id) {
        id
        title
    }
}
~~~

Schema định nghĩa khả năng của API. Operation chọn một phần khả năng đó và chỉ định các field mà client muốn nhận.

## 2. Khai báo field trong type Query

Một field trong object type có cấu trúc tổng quát:

~~~graphql
fieldName(argumentName: ArgumentType): ReturnType
~~~

Ví dụ:

~~~graphql
type Query {
    book(id: ID!): Book
    books: [Book!]!
    totalBooks: Int!
}
~~~

Type Query có thể chứa nhiều field. Mỗi field là một điểm vào độc lập trong schema:

- `book` tìm một quyển sách theo ID.
- `books` trả về danh sách sách.
- `totalBooks` trả về số lượng sách.

Tên field thường dùng lower camelCase, ví dụ `bookById`, `recentBooks`, `totalBooks`. Tên type dùng PascalCase, ví dụ `Book`, `Author`, `BookFilter`. Cách đặt tên nhất quán làm schema dễ đọc và dễ dùng trong công cụ GraphQL.

Một field có thể trả về scalar, enum, object, interface, union hoặc list của các kiểu hợp lệ. Nếu field trả về object, client phải khai báo selection set cho object đó. Nếu field trả về scalar hoặc enum, client không thêm selection set con.

Ví dụ:

~~~graphql
type Query {
    bookTitle(id: ID!): String
    book(id: ID!): Book
}
~~~

Operation:

~~~graphql
query {
    bookTitle(id: "book-42")
    book(id: "book-42") {
        id
        title
    }
}
~~~

Field `bookTitle` trả về scalar `String`, còn field `book` trả về object `Book`, nên operation phải chọn các field con của Book.

## 3. Kiểu dữ liệu trả về và nullability

Kiểu trả về xác định hình dạng dữ liệu mà field có thể cung cấp. GraphQL có các scalar dựng sẵn:

| Scalar | Ý nghĩa |
| --- | --- |
| `Int` | Số nguyên có dấu 32-bit. |
| `Float` | Số thực dấu phẩy động. |
| `String` | Chuỗi ký tự. |
| `Boolean` | Giá trị đúng hoặc sai. |
| `ID` | Định danh; thường được serialize thành chuỗi. |

Ngoài scalar, field có thể trả về object type do ứng dụng định nghĩa:

~~~graphql
type Book {
    id: ID!
    title: String!
}

type Query {
    book(id: ID!): Book
}
~~~

### Dấu ! có ý nghĩa gì?

Mặc định, field và phần tử list có thể nhận giá trị `null`. Thêm dấu `!` sau kiểu dữ liệu nghĩa là giá trị tại vị trí đó không được phép là `null`.

Với field đơn:

~~~graphql
type Query {
    book(id: ID!): Book
    requiredBook(id: ID!): Book!
}
~~~

- `Book` cho phép resolver trả về `null`, ví dụ không tìm thấy sách.
- `Book!` cam kết resolver phải trả về một Book hợp lệ. Nếu kết quả là `null`, GraphQL phát sinh execution error và áp dụng quy tắc lan truyền null.

Dấu `!` của argument cũng có ý nghĩa tương tự nhưng áp dụng cho đầu vào:

~~~graphql
type Query {
    book(id: ID!): Book
    books(keyword: String): [Book!]!
}
~~~

`id: ID!` bắt buộc client cung cấp giá trị khác `null`. `keyword: String` là tùy chọn và có thể không được gửi hoặc nhận `null`.

### Nullability của list

Có bốn cách khai báo thường gặp:

| Kiểu SDL | Ý nghĩa |
| --- | --- |
| `[Book]` | List có thể là `null`; từng phần tử cũng có thể là `null`. |
| `[Book!]` | List có thể là `null`; phần tử không được là `null`. |
| `[Book]!` | List không được là `null`; phần tử có thể là `null`. |
| `[Book!]!` | List không được là `null`; mọi phần tử cũng không được là `null`. |

Ví dụ:

~~~graphql
type Query {
    books: [Book!]!
}
~~~

Field `books` cam kết luôn trả về một list. List có thể rỗng, nhưng không được là `null` và không được chứa phần tử `null`.

Chọn nullability dựa trên hợp đồng nghiệp vụ. Nếu không tìm thấy một quyển sách theo ID là tình huống bình thường, field `book(id: ID!): Book` có thể phù hợp. Nếu endpoint danh sách luôn trả về một collection, kể cả collection rỗng, `[Book!]!` thường diễn đạt rõ hơn.

Khi một field non-null phát sinh lỗi và không thể tạo giá trị, GraphQL không thể thay chính field đó bằng `null`. Null sẽ lan truyền lên field cha gần nhất cho phép null; nếu tất cả field trên đường lan truyền đều non-null, `data` ở root có thể trở thành `null`. Vì vậy, không nên thêm `!` chỉ để schema trông chặt chẽ hơn nếu dữ liệu thực tế không bảo đảm cam kết đó.

## 4. Khai báo argument cho Query field

Argument cho phép client truyền điều kiện vào field. Ví dụ:

~~~graphql
type Query {
    book(id: ID!): Book
    booksByAuthor(authorId: ID!): [Book!]!
}
~~~

Client có thể gọi:

~~~graphql
query {
    book(id: "book-42") {
        id
        title
    }

    booksByAuthor(authorId: "author-7") {
        id
        title
    }
}
~~~

Argument được khai báo bên trong dấu ngoặc đơn sau tên field. Mỗi argument có tên và kiểu dữ liệu. Có thể có nhiều argument trên một field:

~~~graphql
type Query {
    books(
        keyword: String
        genre: BookGenre
        limit: Int = 20
        offset: Int = 0
    ): [Book!]!
}
~~~

Trong ví dụ này:

- `keyword` và `genre` là tùy chọn.
- `limit` mặc định bằng 20 nếu client không truyền.
- `offset` mặc định bằng 0.
- Client có thể truyền một phần hoặc toàn bộ argument.

Giá trị mặc định trong SDL chỉ được dùng khi argument không được cung cấp. Nếu client gửi giá trị `null` cho một argument nullable, giá trị đó vẫn là `null`, không tự động chuyển thành default. Đây là khác biệt cần lưu ý khi thiết kế API.

### Dùng input object cho bộ lọc

Khi một field có nhiều điều kiện tìm kiếm, có thể gom chúng vào input object để request dễ đọc và schema dễ mở rộng:

~~~graphql
enum BookGenre {
    TECHNOLOGY
    SCIENCE
    HISTORY
    FICTION
}

input BookFilter {
    keyword: String
    genre: BookGenre
    authorId: ID
}

type Query {
    books(filter: BookFilter, limit: Int = 20, offset: Int = 0): [Book!]!
}
~~~

Operation:

~~~graphql
query SearchBooks($filter: BookFilter, $limit: Int, $offset: Int) {
    books(filter: $filter, limit: $limit, offset: $offset) {
        id
        title
        genre
    }
}
~~~

Variables:

~~~json
{
    "filter": {
        "keyword": "Spring",
        "genre": "TECHNOLOGY"
    },
    "limit": 10,
    "offset": 0
}
~~~

Input object giúp tránh một field có quá nhiều argument rời rạc. Nó cũng tạo một kiểu đầu vào có thể tái sử dụng giữa các field. Lưu ý input object chỉ chứa các kiểu đầu vào hợp lệ như scalar, enum và input object khác; không dùng output object như `Book` làm kiểu của một input field.

## 5. Một schema Query hoàn chỉnh

Ví dụ sau kết hợp field đơn, danh sách, filter, enum và object lồng nhau:

~~~graphql
enum BookGenre {
    TECHNOLOGY
    SCIENCE
    HISTORY
    FICTION
}

input BookFilter {
    keyword: String
    genre: BookGenre
    authorId: ID
}

type Author {
    id: ID!
    name: String!
}

type Book {
    id: ID!
    title: String!
    genre: BookGenre!
    author: Author
}

type Query {
    book(id: ID!): Book
    books(
        filter: BookFilter
        limit: Int = 20
        offset: Int = 0
    ): [Book!]!
    totalBooks(filter: BookFilter): Int!
}
~~~

Có thể đọc schema theo các nhóm:

- `BookGenre` giới hạn thể loại sách vào các giá trị đã công bố.
- `BookFilter` mô tả điều kiện tìm kiếm.
- `Author` và `Book` là output object types.
- `Query.book` tìm một sách theo ID.
- `Query.books` tìm danh sách sách theo filter và phân trang.
- `Query.totalBooks` trả về tổng số sách thỏa điều kiện lọc.

Client có thể gọi nhiều field trong cùng một query:

~~~graphql
query CatalogOverview($filter: BookFilter) {
    books(filter: $filter, limit: 5) {
        id
        title
        author {
            id
            name
        }
    }

    totalBooks(filter: $filter)
}
~~~

Response có cấu trúc tương ứng với các field được chọn:

~~~json
{
    "data": {
        "books": [
            {
                "id": "book-42",
                "title": "Spring in Action",
                "author": {
                    "id": "author-7",
                    "name": "Lan"
                }
            }
        ],
        "totalBooks": 1
    }
}
~~~

Tên key trong `data` tương ứng với tên field hoặc alias mà client chọn. Client có thể chọn các field cần thiết, không cần nhận toàn bộ thuộc tính của object.

### Alias khi cần gọi cùng một field nhiều lần

Nếu cần gọi cùng một field với các argument khác nhau trong một operation, dùng alias để đặt tên kết quả:

~~~graphql
query CompareBooks {
    first: book(id: "book-42") {
        id
        title
    }

    second: book(id: "book-99") {
        id
        title
    }
}
~~~

Response sẽ có hai key `first` và `second`. Alias giúp tránh xung đột tên field trong kết quả và thể hiện rõ ý nghĩa của từng lần gọi.

## 6. Ánh xạ type Query trong Spring for GraphQL

Sau khi định nghĩa schema, ứng dụng cần cung cấp resolver cho các field trên root Query. Spring for GraphQL hỗ trợ `@QueryMapping` để ánh xạ một method trong controller đến field cùng tên của Query.

Với schema:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

Controller:

~~~java
package com.example.catalog.graphql;

import com.example.catalog.book.Book;
import com.example.catalog.book.BookService;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id);
    }
}
~~~

Các điểm chính:

- `@Controller` đăng ký class với Spring container.
- `@QueryMapping` mặc định ánh xạ method `book` đến field `Query.book`.
- `@Argument("id")` lấy argument có tên `id` trong schema.
- Giá trị trả về của method được GraphQL engine dùng để hoàn thành field trong response.

GraphQL scalar `ID` thường được nhận vào Java dưới dạng `String`. Với các kiểu scalar khác, Spring chuyển đổi giá trị đầu vào sang kiểu Java tương ứng theo cơ chế conversion được cấu hình.

Nếu tên method Java khác tên field trong schema, chỉ rõ tên mapping:

~~~java
@QueryMapping(name = "books")
public List<Book> findCatalogBooks() {
    return bookService.findAll();
}
~~~

Nếu tên tham số Java khác tên argument, ghi rõ tên argument trong annotation:

~~~java
@QueryMapping
public Book bookById(@Argument("id") String bookId) {
    return bookService.findById(bookId);
}
~~~

Cách ghi tên tường minh làm cho mapping dễ đọc và tránh phụ thuộc vào việc giữ lại tên tham số khi biên dịch Java.

### Ánh xạ nhiều argument và input object

Với field có nhiều argument:

~~~graphql
type Query {
    books(keyword: String, limit: Int = 20): [Book!]!
}
~~~

Resolver:

~~~java
@QueryMapping
public List<Book> books(
        @Argument("keyword") String keyword,
        @Argument("limit") Integer limit) {
    return bookService.search(keyword, limit);
}
~~~

Với input object, có thể ánh xạ vào một Java class hoặc record phù hợp:

~~~java
public record BookFilter(String keyword, BookGenre genre, String authorId) {
}
~~~

~~~java
@QueryMapping
public List<Book> books(
        @Argument("filter") BookFilter filter,
        @Argument("limit") Integer limit,
        @Argument("offset") Integer offset) {
    return bookService.search(filter, limit, offset);
}
~~~

Tên và kiểu các thuộc tính đầu vào phải tương thích với input object trong SDL. Với hệ thống lớn, nên kiểm tra rõ cách chuyển đổi enum, ID, ngày giờ và kiểu tùy chỉnh của dự án.

## 7. Phân giải field lồng nhau từ Query result

Field trên Query thường trả về object hoặc list object. Khi client chọn field con, GraphQL tiếp tục phân giải các field trên object đó.

Ví dụ:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    author: Author
}
~~~

Nếu object Book trả về đã có thuộc tính `id` và `title`, GraphQL có thể lấy giá trị từ object thông qua property access. Nếu cần truy vấn tác giả riêng, có thể dùng `@SchemaMapping`:

~~~java
@Controller
public class BookFieldController {

    private final AuthorService authorService;

    public BookFieldController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }
}
~~~

Ở đây `@QueryMapping` xử lý field gốc `Query.book`, còn `@SchemaMapping` xử lý field `Book.author`. Tách hai nhiệm vụ giúp resolver của Query tập trung tìm sách, còn resolver của Book chịu trách nhiệm lấy tác giả.

Nếu Query trả về danh sách nhiều Book và mỗi resolver `author` truy vấn database riêng, ứng dụng có thể phát sinh N+1. Có thể sử dụng DataLoader hoặc `@BatchMapping` để gom các lần tải tác giả thành batch. Thiết kế Query nên xem xét cách các field con được phân giải, vì một operation duy nhất có thể kích hoạt nhiều lần truy cập dữ liệu phía server.

## 8. Mở rộng Query khi schema được chia thành nhiều file

Trong module lớn, schema có thể được tách thành nhiều file theo domain hoặc feature. Khi root type đã được khai báo, file khác có thể bổ sung field bằng `extend type Query`:

Tệp `catalog.graphqls`:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

Tệp `author.graphqls`:

~~~graphql
extend type Query {
    author(id: ID!): Author
}
~~~

`extend type Query` mở rộng object type đã tồn tại. Nó không tạo một root type Query thứ hai. Vì vậy, schema phải có một định nghĩa gốc trước khi các phần mở rộng được hợp nhất. Tất cả schema resource cũng phải được nạp vào cùng GraphQL schema runtime.

Trong Spring Boot, các file SDL thường được đặt trong `src/main/resources/graphql/`. Có thể chia thành thư mục con và cấu hình `spring.graphql.schema.locations` nếu cần thay đổi vị trí tìm kiếm. Khi ứng dụng khởi động, kiểm tra log schema parsing nếu một field mới không xuất hiện trong API.

Không khai báo trùng cùng một field với cùng tên trong nhiều phần schema. Nếu hai module cần cùng tên field nhưng ý nghĩa khác nhau, cần thống nhất hợp đồng API hoặc đặt tên rõ ràng theo domain.

## 9. Thiết kế Query dễ sử dụng và an toàn

Một type Query tốt cần thể hiện rõ mục đích của từng field và giới hạn được cách client truy vấn.

**Đặt tên theo hành vi và domain.** Dùng `book`, `books`, `booksByAuthor` hoặc `searchBooks` khi chúng diễn đạt đúng chức năng. Tránh tên quá chung như `getData` hoặc tên phụ thuộc vào chi tiết repository.

**Dùng argument có kiểu rõ ràng.** Dùng `ID` cho định danh, enum cho tập giá trị hữu hạn và input object cho bộ lọc nhiều thuộc tính. Chỉ đánh dấu non-null khi đầu vào thực sự bắt buộc.

**Thiết kế nullability theo dữ liệu thực tế.** Nếu một bản ghi có thể không tồn tại, field trả về nullable thường phù hợp. Nếu một danh sách luôn tồn tại, có thể trả list rỗng thay vì `null`.

**Đặt giới hạn cho truy vấn danh sách.** SDL có thể khai báo `limit` và `offset`, nhưng resolver vẫn phải kiểm tra giới hạn tối đa, giá trị âm và chi phí truy vấn. Không nên tin mọi giá trị do client truyền vào.

**Giữ Query không tạo side effect.** Query được dùng để đọc dữ liệu. Thao tác làm thay đổi trạng thái nên được khai báo trong root type Mutation, giúp client, cache và hạ tầng hiểu đúng ý nghĩa operation.

**Kiểm soát độ sâu và chi phí truy vấn.** Một query có thể yêu cầu nhiều field lồng nhau hoặc gọi các field có chi phí cao. Ở môi trường production, cân nhắc giới hạn độ sâu, độ phức tạp, timeout, kích thước danh sách và quyền truy cập theo field.

## 10. Các lỗi thường gặp khi khai báo type Query

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Schema không có query root | Thiếu `type Query` hoặc thiếu khai báo `schema { query: ... }` khi dùng tên root khác. | Kiểm tra root operation type trong SDL. |
| Query báo không tìm thấy field | Tên field trong operation không tồn tại trong Query hoặc schema mở rộng chưa được nạp. | Đối chiếu tên field và các file `extend type Query`. |
| Field object báo thiếu selection set | Client yêu cầu object nhưng không chọn field con. | Thêm selection set cho object field. |
| Scalar báo không được có selection set | Client thêm dấu ngoặc nhọn sau scalar hoặc enum. | Chỉ chọn field trực tiếp cho scalar và enum. |
| Thiếu argument bắt buộc | Argument được khai báo non-null nhưng client không truyền giá trị. | Kiểm tra kiểu `!`, operation variables và request variables. |
| Resolver nhận `null` | Tên argument không khớp hoặc giá trị đầu vào thực sự là null. | Kiểm tra `@Argument`, tên argument trong SDL và variables. |
| Field trả về `null` ngoài dự kiến | Resolver không tìm thấy dữ liệu hoặc kiểu trả về cho phép null. | Kiểm tra kết quả service và nullability của field. |
| Query danh sách quá chậm | Không giới hạn kết quả, truy vấn lặp cho field lồng nhau hoặc thiếu index. | Kiểm tra pagination, DataLoader, số truy vấn và kế hoạch thực thi database. |

Khi debug trong Spring for GraphQL, nên kiểm tra schema được nạp trước, sau đó xác minh mapping `@QueryMapping`, tên argument và giá trị trả về của service. Nếu root field chạy đúng nhưng field con chậm hoặc lỗi, kiểm tra resolver `@SchemaMapping` và chiến lược DataLoader tương ứng.

## 11. Kiểm thử Query

Có thể dùng `GraphQlTester` để kiểm tra schema và resolver mà không cần gửi HTTP request thật:

~~~java
@Test
void returnsBookById() {
    graphQlTester.document("""
            query BookDetail($id: ID!) {
                book(id: $id) {
                    id
                    title
                }
            }
            """)
        .variable("id", "book-42")
        .execute()
        .path("book.id")
        .entity(String.class)
        .isEqualTo("book-42");
}
~~~

Nên kiểm thử các trường hợp quan trọng:

- Query có argument hợp lệ trả đúng dữ liệu.
- Không tìm thấy bản ghi trả kết quả nullable theo hợp đồng.
- Thiếu argument non-null bị từ chối trước khi resolver thực thi.
- Filter và phân trang xử lý đúng giá trị biên.
- Field lồng nhau trả đúng dữ liệu và không tạo số lượng truy vấn ngoài dự kiến.
- Người dùng không có quyền không thể đọc field cần bảo vệ.

Kiểm thử schema giúp phát hiện lỗi hợp đồng sớm. Kiểm thử resolver giúp xác nhận logic truy cập dữ liệu. Kiểm thử tích hợp giúp xác nhận toàn bộ luồng từ request đến response.

## 12. Những điểm cần ghi nhớ

- `type Query` là root object type dành cho các thao tác đọc trong GraphQL.
- Mỗi field khai báo argument và kiểu trả về; object field cần selection set khi client truy vấn.
- Dấu `!` quy định giá trị không được null, áp dụng riêng cho argument, field và phần tử list.
- Input object và enum giúp mô hình hóa bộ lọc có cấu trúc.
- Spring for GraphQL ánh xạ root field bằng `@QueryMapping`; field lồng nhau có thể dùng `@SchemaMapping` hoặc `@BatchMapping`.
- Có thể mở rộng root Query từ nhiều file SDL bằng `extend type Query`.
- Thiết kế Query cần chú ý pagination, nullability, quyền truy cập và chi phí truy vấn phía server.

Type Query là cửa vào của phần đọc dữ liệu trong GraphQL API. Khi field, argument và kiểu trả về được thiết kế đúng, client có thể lấy chính xác dữ liệu cần dùng, còn ứng dụng Spring for GraphQL có hợp đồng rõ ràng để triển khai, kiểm thử và tối ưu resolver.

