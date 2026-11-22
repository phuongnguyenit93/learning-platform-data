# Query trả về object

Trong GraphQL, một query field có thể trả về một object type thay vì chỉ trả về scalar như `String`, `Int` hoặc `Boolean`. Cách thiết kế này cho phép client lấy một đối tượng cùng những field con cần thiết trong một operation, ví dụ lấy một cuốn sách cùng tác giả, thể loại và thông tin xuất bản.

Với Spring for GraphQL, method được đánh dấu `@QueryMapping` có thể trả về một object Java. GraphQL runtime tiếp tục xử lý selection set của object đó: các field đơn giản có thể được đọc từ thuộc tính của object, còn field cần logic riêng có thể được ánh xạ bằng `@SchemaMapping` hoặc cơ chế batch loading.

## 1. Khai báo object type và query field trong SDL

Giả sử ứng dụng thư viện cần tìm một cuốn sách theo ID. Schema có thể khai báo:

```graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    description: String
    publishedYear: Int
}
```

Ở đây:

- `Query.book` là field ở root query type, nhận argument `id` và trả về một `Book`.
- `Book` là object type, mô tả các field mà client có thể chọn.
- `Book` không có dấu `!` ở kiểu trả về, nên field `book` được phép trả `null`, chẳng hạn khi không tìm thấy sách.
- `id` và `title` là non-null, nghĩa là một object `Book` hợp lệ phải cung cấp hai field này.
- `description` và `publishedYear` có thể là null.

Object type là output type. Nó được dùng để mô tả dữ liệu server trả về, không dùng làm kiểu argument hoặc field trong input object. Nếu client cần gửi dữ liệu dạng object, hãy khai báo một `input` type riêng.

## 2. Client phải chọn field của object

Khác với scalar, object type cần một selection set để chỉ rõ các field con muốn nhận. Query sau không hợp lệ vì `book` trả về `Book` nhưng không có selection set:

```graphql
query {
    book(id: "book-42")
}
```

Query hợp lệ:

```graphql
query {
    book(id: "book-42") {
        id
        title
        publishedYear
    }
}
```

Client có thể chọn ít field hoặc nhiều field tùy nhu cầu. Nếu màn hình chỉ cần tiêu đề, query có thể ngắn hơn:

```graphql
query {
    book(id: "book-42") {
        title
    }
}
```

Schema vẫn giữ nguyên. Client thay đổi selection set mà không cần server tạo một endpoint response riêng cho từng màn hình.

## 3. Ánh xạ Query trả về object với @QueryMapping

Spring for GraphQL dùng `@QueryMapping` để ánh xạ method controller vào field cùng tên trong root type `Query`. Ví dụ với SDL ở trên:

```java
package com.example.graphql.book;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id);
    }
}
```

Method `book` được ánh xạ vào `Query.book`. Annotation `@Argument("id")` lấy giá trị argument `id` từ GraphQL field. Method trả về một object Java `Book`; Spring for GraphQL chuyển kết quả đó cho GraphQL execution để tiếp tục resolve các field client đã chọn.

Nếu tên method khác tên field trong SDL, chỉ định tên rõ ràng:

```java
@QueryMapping(name = "book")
public Book findBookById(@Argument("id") String id) {
    return bookService.findById(id);
}
```

Tên argument phải khớp schema. Nên ghi rõ tên trong `@Argument` khi muốn code không phụ thuộc vào metadata tên parameter được compiler giữ lại.

## 4. Định nghĩa Java object phù hợp với GraphQL type

Một object Java có thể cung cấp dữ liệu cho GraphQL object type. Ví dụ dùng Java record:

```java
public record Book(
    String id,
    String title,
    String description,
    Integer publishedYear
) {}
```

GraphQL Java có thể đọc các thuộc tính từ object nguồn thông qua property data fetcher mặc định. Với record, các accessor như `id()` và `title()` cung cấp giá trị tương ứng; với JavaBean, thường dùng getter như `getId()` và `getTitle()`.

Tên thuộc tính nguồn cần tương ứng với tên field GraphQL hoặc được ánh xạ bằng resolver riêng. Ví dụ `publishedYear` trong SDL có thể được đọc từ thuộc tính `publishedYear` của record hoặc getter `getPublishedYear()` của JavaBean.

Không bắt buộc tên class Java phải giống tên GraphQL type, nhưng việc đặt tên nhất quán giúp code dễ đọc. Nếu model persistence có cấu trúc khác hợp đồng API, nên chuyển sang DTO hoặc projection phù hợp thay vì buộc GraphQL schema phụ thuộc trực tiếp vào entity database.

## 5. GraphQL xử lý object trả về như thế nào?

Khi `@QueryMapping` trả về một object `Book`, GraphQL runtime không tự động biến object thành JSON bằng cách serialize toàn bộ thuộc tính. Runtime thực thi selection set mà client đã yêu cầu.

Ví dụ client gửi:

```graphql
query BookDetail($id: ID!) {
    book(id: $id) {
        id
        title
        description
    }
}
```

Variables:

```json
{
  "id": "book-42"
}
```

Luồng xử lý khái quát:

```mermaid
flowchart TD
    A[Client gửi query và variables] --> B[GraphQL chọn Query.book]
    B --> C[@QueryMapping gọi BookController.book]
    C --> D[BookService tìm Book]
    D --> E[Trả object Book]
    E --> F[Resolve field id]
    E --> G[Resolve field title]
    E --> H[Resolve field description]
    F --> I[Ghép response theo selection set]
    G --> I
    H --> I
    I --> J[Trả GraphQL response]
```

Response ví dụ:

```json
{
  "data": {
    "book": {
      "id": "book-42",
      "title": "Spring GraphQL thực hành",
      "description": "Xây dựng GraphQL API với Spring."
    }
  }
}
```

Nếu client chỉ chọn `id` và `title`, GraphQL chỉ đưa hai field đó vào response. Tuy nhiên, việc chỉ trả một số field không bảo đảm repository chỉ đọc đúng các cột đó; muốn tối ưu truy vấn database theo selection set cần thiết kế projection hoặc data access riêng.

## 6. Query trả về object có field lồng nhau

Một object type có thể chứa field là object type khác. Ví dụ sách có tác giả:

```graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    author: Author
}

type Author {
    id: ID!
    name: String!
    biography: String
}
```

Client có thể lấy sách và tác giả trong cùng operation:

```graphql
query BookDetail($id: ID!) {
    book(id: $id) {
        id
        title
        author {
            id
            name
        }
    }
}
```

Nếu object `Book` trả về đã có thuộc tính `author` chứa một object `Author`, property data fetcher mặc định có thể đọc thuộc tính đó. Không cần viết resolver cho mọi field nếu dữ liệu đã có sẵn và việc truy cập thuộc tính là đủ.

Khi field cần logic riêng, ví dụ chỉ có `authorId` trong `Book` và phải gọi service để tải tác giả, dùng `@SchemaMapping`:

```java
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
```

Tham số `Book book` là source object được trả về từ resolver cha. `@SchemaMapping` đăng ký cách resolve field `Book.author` từ object đó.

## 7. Query trả về object có danh sách object con

Object có thể chứa một danh sách các object khác. Ví dụ một tác giả có nhiều sách:

```graphql
type Query {
    author(id: ID!): Author
}

type Author {
    id: ID!
    name: String!
    books: [Book!]!
}

type Book {
    id: ID!
    title: String!
}
```

Query:

```graphql
query AuthorDetail($id: ID!) {
    author(id: $id) {
        id
        name
        books {
            id
            title
        }
    }
}
```

Kiểu `[Book!]!` có nghĩa field `books` luôn trả về một danh sách khác null và từng phần tử trong danh sách cũng không null. Danh sách rỗng `[]` là hợp lệ nếu tác giả chưa có sách.

Nếu số lượng phần tử có thể lớn, nên thiết kế phân trang bằng argument hoặc connection type. Trả về toàn bộ collection không giới hạn có thể làm response lớn, tăng thời gian truy vấn và bộ nhớ.

## 8. Nullability và trường hợp không tìm thấy object

Nullability trong SDL quyết định server cam kết điều gì với client.

| SDL | Ý nghĩa |
| --- | --- |
| `book: Book` | Field có thể trả một Book hoặc null |
| `book: Book!` | Field phải trả một Book khác null |
| `books: [Book]` | Danh sách có thể null và phần tử cũng có thể null |
| `books: [Book!]` | Danh sách có thể null, phần tử không được null |
| `books: [Book!]!` | Danh sách và mọi phần tử đều không được null |

Với query tìm theo ID, thường có hai lựa chọn hợp đồng:

1. Khai báo `book: Book` và trả null khi không tìm thấy. Client kiểm tra `data.book`.
2. Khai báo `book: Book!` và ném exception nghiệp vụ khi không tìm thấy, sau đó ánh xạ lỗi sang GraphQL error phù hợp.

Không nên khai báo non-null rồi âm thầm trả null. Nếu một field non-null trả null hoặc phát sinh lỗi, GraphQL tạo execution error và lan truyền null lên field cha gần nhất có thể nhận null. Nếu lỗi lan đến root `data`, toàn bộ `data` có thể trở thành null.

Ví dụ với `book: Book`:

```json
{
  "data": {
    "book": null
  }
}
```

Nếu service ném exception, response có thể chứa `errors` cùng `data` một phần tùy vị trí lỗi và nullability. Hãy thống nhất cách biểu diễn not found, validation failure và lỗi hệ thống để client không phải đoán.

## 9. Dùng Optional và kiểu trả về bất đồng bộ

Resolver có thể trả về object đồng bộ. Spring for GraphQL cũng hỗ trợ nhiều kiểu kết quả bất đồng bộ và reactive.

Ví dụ dùng `CompletableFuture`:

```java
@QueryMapping
public CompletableFuture<Book> book(@Argument("id") String id) {
    return bookService.findByIdAsync(id);
}
```

Với ứng dụng reactive, có thể trả `Mono<Book>` khi sử dụng stack và dependency tương ứng. Chọn kiểu trả về theo cách service thực sự thực hiện công việc; bọc một lời gọi blocking trong `CompletableFuture` không tự biến nó thành I/O non-blocking.

Nếu service trả `Optional<Book>`, hãy chuyển đổi rõ ràng ở controller hoặc service boundary theo hợp đồng nullability mà API muốn cung cấp, ví dụ `orElse(null)` cho field nullable hoặc ném exception nghiệp vụ để tạo GraphQL error đã chuẩn hóa. Không dựa vào một kiểu wrapper mà chưa xác nhận nó được adapter đang dùng hỗ trợ, và không dùng `Optional` để che giấu lỗi hệ thống.

## 10. Phân biệt Query resolver và field resolver

Một operation có thể kích hoạt nhiều resolver:

- `@QueryMapping` resolve field ở root type `Query`, ví dụ `Query.book`.
- `@SchemaMapping` resolve field của một object type, ví dụ `Book.author`.
- Property data fetcher mặc định đọc field từ object nguồn nếu không có resolver tùy chỉnh phù hợp.

Ví dụ query:

```graphql
query {
    book(id: "book-42") {
        id
        title
        author {
            name
        }
    }
}
```

`BookController.book` tải object sách. Sau đó GraphQL resolve `id`, `title` và `author` trên object `Book`. Nếu `author` cần truy cập service riêng, `BookFieldController.author` xử lý field đó; field `Author.name` tiếp tục được resolve từ object `Author` hoặc resolver tương ứng.

Việc tách resolver theo field giúp mỗi phần của schema chịu trách nhiệm cho dữ liệu của mình. Tuy nhiên, nếu mỗi field con gọi database riêng cho từng object cha, query có thể gặp vấn đề N+1.

## 11. Tránh N+1 khi object có quan hệ dữ liệu

Giả sử query trả về 30 sách và mỗi sách có field `author`. Nếu `@SchemaMapping` gọi `authorService.findById()` một lần cho từng sách, server có thể thực hiện 30 lần truy vấn tác giả sau khi tải danh sách sách.

Có thể dùng `@BatchMapping` để gom các yêu cầu theo lô:

```java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> author(List<Book> books) {
    return authorService.findByBooks(books);
}
```

Hoặc dùng `BatchLoaderRegistry`/DataLoader khi cần kiểm soát batch loading chi tiết hơn. Batch loader nên trả kết quả ánh xạ đúng với từng key/source và xử lý rõ trường hợp không tìm thấy dữ liệu liên quan.

Một HTTP request GraphQL không đồng nghĩa với một truy vấn database. Khi tối ưu query trả về object, cần đo số resolver, số truy vấn database, số lời gọi service, kích thước response và độ trễ tổng thể.

## 12. Kiểm thử Query trả về object với GraphQlTester

`GraphQlTester` cho phép thực thi query và kiểm tra từng đường dẫn trong response. Ví dụ:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;

@GraphQlTest(BookController.class)
class BookControllerTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void returnsBookObject() {
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
}
```

Ví dụ giả định test context cung cấp `BookService` mock hoặc test bean trả về sách có ID `book-42`. Có thể kiểm tra thêm `book.title`, field lồng nhau, trường hợp không tìm thấy và GraphQL errors.

Các trường hợp nên kiểm thử:

- Query có selection set đúng và sai.
- Argument ID hợp lệ, không hợp lệ hoặc không tìm thấy object.
- Client chọn ít field và nhiều field khác nhau.
- Object có field con được resolve mặc định và field con có `@SchemaMapping`.
- Nullability của object và field lồng nhau.
- Danh sách object rỗng, có phần tử và phân trang.
- Exception từ service và cách lỗi lan truyền theo nullability.
- Batch loading khi trả về nhiều object có quan hệ.

Slice test tập trung vào GraphQL controller. Khi cần xác minh schema resource, auto-configuration, security, database và HTTP transport cùng hoạt động, hãy bổ sung integration test với application context phù hợp.

## 13. Lỗi thường gặp khi Query trả về object

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Query bị từ chối vì thiếu selection set | Field trả object nhưng client không chọn field con | Thêm `{ ... }` với các field cần thiết |
| `Unknown type` hoặc sai schema | Object type chưa khai báo hoặc tên type sai | Kiểm tra SDL và schema resources |
| Controller không được gọi | Method không được ánh xạ hoặc controller không phải Spring bean | Kiểm tra `@Controller`, component scan và `@QueryMapping` |
| Argument nhận null | Tên argument không khớp SDL | Dùng `@Argument("id")` tường minh |
| Field con trả null | Property không tồn tại, getter/accessor không khớp hoặc resolver sai | Kiểm tra source object và mapping field |
| Lỗi non-null lan lên object cha | Resolver trả null hoặc phát sinh lỗi tại field non-null | Điều chỉnh hợp đồng nullability hoặc xử lý lỗi đúng |
| Query chậm khi lấy quan hệ | N+1 hoặc tải quá nhiều dữ liệu | Dùng batch loading, phân trang và đo truy vấn |
| Response có field thừa hoặc dữ liệu nhạy cảm | Resolver trả object chứa field không được kiểm soát đúng | Thiết kế schema, authorization và DTO phù hợp |

## 14. Checklist thiết kế Query trả về object

- Query field đã trả về đúng object type theo hợp đồng API?
- Client có selection set phù hợp với nhu cầu màn hình?
- Argument và `@Argument` đã khớp tên, kiểu và nullability?
- Java object/DTO cung cấp các property tương ứng với GraphQL fields?
- Field lồng nhau đã xác định rõ dùng property fetcher hay `@SchemaMapping`?
- Trường hợp không tìm thấy object đã có hợp đồng null/error rõ ràng?
- Nullability của object, field con và list phản ánh đúng khả năng dữ liệu?
- Quan hệ dữ liệu đã được kiểm tra nguy cơ N+1?
- Danh sách lớn đã có phân trang và giới hạn phù hợp?
- Test đã bao phủ object result, nested field, nullability và lỗi?

Query trả về object là cách GraphQL biểu diễn dữ liệu có cấu trúc và quan hệ. `@QueryMapping` trong Spring for GraphQL lấy object gốc, sau đó runtime thực thi từng field trong selection set bằng property fetcher mặc định hoặc resolver được đăng ký. Thiết kế tốt cần thống nhất SDL với DTO, xác định nullability rõ ràng, xử lý field lồng nhau có chủ đích và kiểm soát chi phí truy vấn. Khi làm được điều đó, client có thể lấy đúng cấu trúc dữ liệu cần thiết trong một operation mà server vẫn giữ được logic nghiệp vụ và khả năng tối ưu riêng.
