# Client chọn đúng dữ liệu cần nhận

Một màn hình danh sách sách thường chỉ cần mã sách, tiêu đề và tên tác giả. Màn hình chi tiết lại cần thêm phần giới thiệu, năm xuất bản, thẻ chủ đề và thông tin đầy đủ của tác giả. Nếu API luôn trả về toàn bộ dữ liệu cho cả hai màn hình, client phải nhận và xử lý nhiều trường không dùng đến. Nếu API chỉ trả về một cấu trúc cố định cho từng màn hình, backend có thể phải tạo nhiều endpoint gần giống nhau.

GraphQL giải quyết vấn đề này bằng **selection set**: trong mỗi operation, client khai báo chính xác các field muốn nhận. Server kiểm tra yêu cầu dựa trên schema, thực thi những field được chọn và trả về dữ liệu có hình dạng tương ứng. Cách làm này là một nền tảng quan trọng khi xây dựng API bằng Spring for GraphQL: schema mô tả dữ liệu có thể truy vấn, còn các resolver cung cấp giá trị cho những field mà operation yêu cầu.

Sau bài học, bạn có thể đọc và viết selection set, chọn field lồng nhau, truyền arguments bằng variables, đổi tên field bằng alias, tái sử dụng fragment và hiểu cách các lựa chọn đó được thực thi ở server.

## 1. Selection set quyết định hình dạng dữ liệu trả về

Một GraphQL operation gồm tên operation, các arguments nếu cần và một tập field nằm trong cặp dấu ngoặc nhọn. Tập field này được gọi là selection set.

Xét schema SDL đơn giản của một ứng dụng quản lý sách:

```graphql
type Query {
  book(id: ID!): Book
  books(limit: Int = 20, offset: Int = 0): [Book!]!
  searchBooks(keyword: String!, limit: Int = 10): [Book!]!
}

type Book {
  id: ID!
  title: String!
  summary: String
  publishedYear: Int
  tags: [String!]!
  author: Author!
}

type Author {
  id: ID!
  name: String!
  biography: String
}
```

Schema cho biết `Query` có thể cung cấp một sách, danh sách sách hoặc kết quả tìm kiếm. Mỗi `Book` có các field như `id`, `title`, `summary` và `author`. `author` là một object có kiểu `Author`, vì vậy client có thể tiếp tục chọn các field bên trong tác giả.

Ví dụ, màn hình chỉ cần tiêu đề và tên tác giả có thể gửi query:

```graphql
query BookSummary {
  book(id: "book-42") {
    title
    author {
      name
    }
  }
}
```

Server trả về cấu trúc tương ứng với những field đã chọn:

```json
{
  "data": {
    "book": {
      "title": "GraphQL nhập môn",
      "author": {
        "name": "Nguyễn An"
      }
    }
  }
}
```

Các field `id`, `summary`, `publishedYear` và `tags` không xuất hiện trong response vì query không yêu cầu chúng. Field không được chọn sẽ bị lược khỏi object trả về; điều này khác với field được chọn nhưng có giá trị `null`.

Selection set cũng áp dụng cho từng phần tử của một danh sách. Query sau yêu cầu server trả về danh sách sách, mỗi phần tử chỉ có mã, tiêu đề và tên tác giả:

```graphql
query BookList {
  books {
    id
    title
    author {
      name
    }
  }
}
```

Client không cần khai báo một kiểu response riêng cho danh sách và một kiểu khác cho chi tiết. Cùng một schema có thể phục vụ nhiều màn hình với selection set khác nhau.

## 2. Chọn field scalar và field object

GraphQL phân biệt field có giá trị scalar với field trả về một object hoặc danh sách object.

- **Scalar** như `String`, `Int`, `Float`, `Boolean` và `ID` là giá trị cuối. Client chọn field scalar trực tiếp, không đặt selection set con bên trong.
- **Object** như `Book` hoặc `Author` cần selection set con để chỉ rõ các field muốn nhận.
- **Danh sách object** cũng cần selection set con cho kiểu object của từng phần tử.

Query hợp lệ:

```graphql
query BookDetail {
  book(id: "book-42") {
    id
    title
    author {
      id
      name
      biography
    }
  }
}
```

Các cách viết sau không hợp lệ:

```graphql
# Sai: author là object nhưng không có selection set con.
query {
  book(id: "book-42") {
    title
    author
  }
}

# Sai: title là scalar nên không thể chọn field con.
query {
  book(id: "book-42") {
    title {
      length
    }
  }
}
```

GraphQL kiểm tra những lỗi về kiểu và cấu trúc này trước khi thực thi resolver. Client cũng không thể tự yêu cầu một field chưa được khai báo trong schema, chẳng hạn `isbn` nếu kiểu `Book` không có field đó. Schema là hợp đồng chung giữa client và server về tên field, kiểu dữ liệu, arguments và khả năng null.

## 3. Arguments chọn đối tượng cần truy vấn, selection set chọn dữ liệu cần nhận

Arguments và selection set giải quyết hai câu hỏi khác nhau:

- **Arguments** xác định dữ liệu hoặc phạm vi dữ liệu cần truy vấn.
- **Selection set** xác định các field cần lấy trên dữ liệu đó.

Ví dụ, `limit` và `offset` chọn một đoạn trong danh sách sách; `id` xác định một sách cụ thể. Các field nằm trong dấu ngoặc nhọn xác định nội dung của từng kết quả.

```graphql
query BookList {
  books(limit: 5, offset: 0) {
    id
    title
  }
}
```

Khi gửi dữ liệu động, nên khai báo variables thay vì ghép giá trị trực tiếp vào chuỗi query:

```graphql
query SearchBooks($keyword: String!, $limit: Int = 10) {
  searchBooks(keyword: $keyword, limit: $limit) {
    id
    title
    author {
      name
    }
  }
}
```

Phần variables được gửi riêng trong payload:

```json
{
  "keyword": "GraphQL",
  "limit": 5
}
```

`String!` có nghĩa là biến `keyword` bắt buộc có giá trị khác `null`. `Int = 10` khai báo giá trị mặc định cho `limit` nếu client không truyền biến này. Kiểu của variable phải tương thích với kiểu argument mà schema khai báo.

Tách variables khỏi query giúp tái sử dụng cùng một operation cho nhiều giá trị đầu vào, làm query dễ đọc và tránh tự nối chuỗi dữ liệu người dùng vào câu lệnh. Khi kiểm tra một request, cần xem cả document và variables vì hai phần cùng quyết định operation thực thi.

## 4. Dùng alias khi cần nhiều kết quả từ cùng một field

Alias cho phép client đặt tên response key khác với tên field trong schema. Alias hữu ích khi một operation cần gọi cùng một field nhiều lần với arguments khác nhau, hoặc khi muốn tên key trong JSON rõ nghĩa hơn.

Ví dụ lấy hai trang sách trong cùng một request:

```graphql
query BookPages {
  firstPage: books(limit: 5, offset: 0) {
    id
    title
  }
  nextPage: books(limit: 5, offset: 5) {
    id
    title
  }
}
```

Response dùng alias làm key:

```json
{
  "data": {
    "firstPage": [
      { "id": "book-1", "title": "GraphQL nhập môn" }
    ],
    "nextPage": [
      { "id": "book-6", "title": "Thiết kế API" }
    ]
  }
}
```

Alias cũng có thể đổi tên một field đơn lẻ:

```graphql
query BookTitle {
  book(id: "book-42") {
    displayTitle: title
  }
}
```

Trong schema, field vẫn là `title`; trong response, key sẽ là `displayTitle`. Alias chỉ đổi tên field trong kết quả, không tạo thêm field mới trên server và không thay đổi cách resolver được ánh xạ.

Nếu gọi cùng một field nhiều lần với arguments khác nhau mà không dùng alias, GraphQL có thể báo lỗi xung đột vì các field cùng tên không thể cùng tạo ra một key kết quả có ý nghĩa duy nhất. Hãy dùng alias để phân biệt các kết quả đó.

## 5. Tái sử dụng selection set bằng fragment

Khi nhiều query cùng cần thông tin cơ bản của một kiểu, việc lặp lại các field dễ làm tài liệu dài và khó đồng bộ. Fragment cho phép đặt một nhóm field dùng chung thành một phần có tên.

```graphql
fragment BookCardFields on Book {
  id
  title
  author {
    name
  }
}

query HomePage {
  books(limit: 8) {
    ...BookCardFields
  }
}

query SearchPage($keyword: String!) {
  searchBooks(keyword: $keyword, limit: 10) {
    ...BookCardFields
  }
}
```

`BookCardFields` áp dụng cho kiểu `Book`, nên có thể được dùng tại những vị trí mà schema yêu cầu một `Book`. Cú pháp `...BookCardFields` đưa các field trong fragment vào selection set hiện tại. Khi server trả kết quả, fragment không tạo thêm một lớp object; các field được trải trực tiếp vào object tương ứng.

Fragment giúp các màn hình dùng chung một cấu trúc dữ liệu nhất quán. Tuy nhiên, không nên gom mọi field có thể có vào một fragment lớn rồi dùng ở tất cả màn hình. Làm vậy sẽ khiến query nhỏ cũng yêu cầu nhiều dữ liệu không cần thiết. Hãy tạo fragment theo mục đích hiển thị, ví dụ `BookCardFields` cho thẻ danh sách và `BookDetailFields` cho trang chi tiết.

## 6. Mutation và Subscription cũng chọn field trả về

Selection set không chỉ dùng với Query. Mutation và Subscription cũng có field trả về, vì vậy client vẫn phải khai báo các field muốn nhận.

Ví dụ schema có mutation cập nhật tiêu đề:

```graphql
type Mutation {
  updateBookTitle(id: ID!, title: String!): Book!
}
```

Client có thể yêu cầu mutation trả về mã, tiêu đề mới và tên tác giả:

```graphql
mutation UpdateBookTitle($id: ID!, $title: String!) {
  updateBookTitle(id: $id, title: $title) {
    id
    title
    author {
      name
    }
  }
}
```

Tương tự, một subscription theo dõi sách được cập nhật có thể chọn phần dữ liệu cần nhận trong mỗi sự kiện:

```graphql
subscription WatchBook($id: ID!) {
  bookUpdated(id: $id) {
    id
    title
  }
}
```

Việc chọn field cho payload giúp client nhận đúng thông tin cần xử lý khi mutation hoàn tất hoặc khi có sự kiện subscription mới.

## 7. Selection set được thực thi như thế nào trong Spring for GraphQL?

Trong Spring for GraphQL, schema SDL định nghĩa field có thể truy vấn. Các method gắn `@QueryMapping`, `@MutationMapping` hoặc `@SubscriptionMapping` thường xử lý field gốc của operation. Field lồng nhau có thể được xử lý bằng `@SchemaMapping`; nếu object nguồn đã có thuộc tính tương ứng, cơ chế truy cập thuộc tính mặc định có thể cung cấp giá trị mà không cần viết resolver riêng.

Ví dụ, schema khai báo `book` và field `Book.author`:

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

Controller có thể cung cấp sách và phân giải tác giả như sau:

```java
@Controller
public class BookController {

    private final BookService bookService;
    private final AuthorService authorService;

    public BookController(
            BookService bookService,
            AuthorService authorService) {
        this.bookService = bookService;
        this.authorService = authorService;
    }

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id);
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }
}
```

Với query chỉ chọn `book { title }`, GraphQL cần giá trị của field `book` và `title`. Resolver `author` không cần được gọi vì client không yêu cầu field đó. Với query chọn thêm `author { name }`, GraphQL tiếp tục phân giải `Book.author`, sau đó lấy `Author.name`.

Đây là lý do selection set có thể giúp server tránh xử lý những field không được yêu cầu. Nhưng cần hiểu đúng giới hạn: GraphQL không tự động biến selection set thành câu SQL chỉ lấy đúng các cột. Nếu `bookService.findById` tải cả entity từ database, các cột đó vẫn có thể được đọc dù response chỉ chứa `title`. Muốn tối ưu truy vấn database, ứng dụng cần thiết kế projection, DTO, repository query hoặc cơ chế tải dữ liệu phù hợp.

### Field lồng nhau và vấn đề N+1

Giả sử query lấy 20 sách và chọn `author { name }`. Resolver `author` đơn giản ở trên có thể được gọi cho từng sách. Nếu mỗi lần gọi lại phát sinh một truy vấn database riêng, server có thể thực hiện một truy vấn lấy danh sách sách và thêm 20 truy vấn lấy tác giả. Đây là vấn đề N+1.

Spring for GraphQL hỗ trợ `@BatchMapping` để gom việc phân giải field lồng nhau theo một nhóm nguồn. Ví dụ dưới đây minh họa ý tưởng: service tải các tác giả theo tập ID, sau đó ánh xạ từng sách với tác giả tương ứng.

```java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> author(List<Book> books) {
    Map<String, Author> authorsById = authorService.findByIds(
            books.stream()
                    .map(Book::authorId)
                    .collect(Collectors.toSet())
    );

    return books.stream().collect(Collectors.toMap(
            Function.identity(),
            book -> authorsById.get(book.authorId())
    ));
}
```

Ví dụ giả định `findByIds` trả về `Map<String, Author>` theo ID tác giả. Trong ứng dụng thực tế, cần xử lý trường hợp thiếu tác giả và bảo đảm kiểu khóa của map phù hợp với kiểu nguồn. DataLoader cũng giải quyết bài toán gom và lưu tạm kết quả tải dữ liệu trong phạm vi một request GraphQL.

Selection set cho biết field nào cần được phân giải; `@BatchMapping` hoặc DataLoader giúp việc phân giải các field đó hiệu quả hơn khi có nhiều object nguồn. Vì vậy, chọn ít field hơn có thể giảm payload và số resolver được gọi, nhưng vẫn cần quan sát truy vấn database và chi phí thực tế của từng field.

## 8. Kiểm thử query và hình dạng response

Khi viết test cho GraphQL API, hãy gửi đúng document mà client sử dụng và kiểm tra các field quan trọng trong response. `GraphQlTester` cho phép thực thi document, truyền variables và đọc kết quả theo đường dẫn.

```java
graphQlTester.document("""
        query BookSummary($id: ID!) {
            book(id: $id) {
                id
                title
                author {
                    name
                }
            }
        }
        """)
    .variable("id", "book-42")
    .execute()
    .path("book.title")
    .entity(String.class)
    .isEqualTo("GraphQL nhập môn");
```

Có thể kiểm tra thêm `book.author.name`, trường hợp ID không tồn tại, giá trị nullable và lỗi do resolver phát sinh. Nên có test cho cả selection set nông và selection set có field lồng nhau để xác nhận các resolver hoạt động đúng.

## 9. Cách đọc response: field bị lược, field null và lỗi

Ba trường hợp sau có ý nghĩa khác nhau:

1. **Field không được chọn:** key không xuất hiện trong object response. Ví dụ query không chọn `summary`, nên response không có key `summary`.
2. **Field được chọn và có kiểu nullable nhưng không có giá trị:** key xuất hiện với giá trị `null`.
3. **Field được khai báo non-null nhưng resolver trả về null hoặc phát sinh lỗi khi phân giải:** GraphQL tạo lỗi và áp dụng quy tắc lan truyền null đến field cha gần nhất có thể nhận null. Vì vậy, một phần dữ liệu trong response có thể bị null dù các field khác vẫn thành công.

GraphQL có thể trả đồng thời `data` và `errors`. Client nên kiểm tra cả hai khi xử lý response, đặc biệt với query có nhiều field lồng nhau. Không nên xem một key bị lược khỏi response là lỗi dữ liệu; trước hết hãy kiểm tra selection set của request.

## 10. Những lỗi thường gặp khi chọn dữ liệu

| Biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `Cannot query field ...` | Field không tồn tại trên kiểu trong schema hoặc sai tên field | Kiểm tra schema, chính tả và kiểu của object cha |
| `Field ... must have a selection of subfields` | Chọn một field object nhưng không khai báo selection set con | Thêm các field cần nhận bên trong `{ ... }` |
| `Field ... must not have a selection since type ... has no subfields` | Đặt selection set con cho scalar | Chọn trực tiếp scalar field |
| Response không có một key mong đợi | Field chưa được chọn hoặc response key đã được đổi bằng alias | Kiểm tra selection set và alias |
| Query trả quá nhiều dữ liệu | Fragment dùng chung chứa nhiều field không cần cho màn hình hiện tại | Tạo fragment theo mục đích hiển thị và chọn đúng field |
| Query có payload nhỏ nhưng vẫn chậm | Resolver hoặc truy vấn database của field được chọn tốn kém; có thể có N+1 | Đo thời gian resolver, tối ưu truy vấn và dùng batching/DataLoader khi phù hợp |

## 11. Nguyên tắc thiết kế selection set

- Bắt đầu từ dữ liệu mà màn hình hoặc tác vụ thực sự sử dụng. Với danh sách, thường chỉ cần ID, tiêu đề và vài field tóm tắt; trang chi tiết mới cần dữ liệu sâu hơn.
- Chỉ mở rộng selection set qua object lồng nhau khi UI cần những field đó. Một field object không bắt buộc phải lấy toàn bộ field con.
- Dùng variables cho dữ liệu đầu vào và alias khi cần nhiều kết quả cùng loại trong một operation.
- Dùng fragment cho nhóm field thực sự được chia sẻ giữa các màn hình. Giữ fragment vừa đủ nhỏ để không vô tình mở rộng dữ liệu của mọi query.
- Phân trang danh sách lớn bằng arguments như `limit` và cursor hoặc offset phù hợp. Không yêu cầu một danh sách không giới hạn chỉ vì client có thể chọn ít field.
- Đánh giá chi phí ở phía server. Một field có thể gọi dịch vụ ngoài, truy vấn database hoặc thực hiện tính toán đắt tiền dù response chỉ chứa một giá trị scalar.
- Kết hợp giới hạn độ sâu, giới hạn độ phức tạp query, xác thực và phân quyền ở cấp field khi phù hợp. Việc client được quyền chọn field không có nghĩa mọi field đều được phép truy cập.

## 12. Bài tập thực hành

Giả sử màn hình thẻ sách cần hiển thị tiêu đề, năm xuất bản và tên tác giả. Hãy viết query lấy tối đa 10 sách, dùng variable cho giới hạn và không lấy `summary` hoặc `biography`.

Một lời giải có thể là:

```graphql
query BookCards($limit: Int = 10) {
  books(limit: $limit) {
    id
    title
    publishedYear
    author {
      name
    }
  }
}
```

Tiếp theo, mở rộng query để lấy thêm phần giới thiệu tác giả khi người dùng mở trang chi tiết. Hãy cân nhắc tạo fragment riêng cho thẻ sách và trang chi tiết. Sau đó viết test bằng `GraphQlTester` để xác nhận field `author.name` được trả về và kiểm tra resolver `author` không bị gọi trong query chỉ lấy `id` và `title`.

Khi hoàn thành, bạn cần nhớ rằng client mô tả dữ liệu mong muốn bằng selection set; schema giới hạn những field có thể chọn; resolver trong Spring for GraphQL cung cấp giá trị cho field được yêu cầu. Thiết kế selection set tốt giúp response gọn và phù hợp với từng màn hình, còn hiệu năng thực tế phụ thuộc thêm vào cách server tải và xử lý dữ liệu.
