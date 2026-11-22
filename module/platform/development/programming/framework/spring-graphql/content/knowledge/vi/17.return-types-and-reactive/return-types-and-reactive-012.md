# Mapping null result

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích ý nghĩa của kết quả null khi GraphQL phân giải một field.
- Phân biệt field nullable và non-null trong schema SDL.
- Hiểu cách GraphQL lan truyền null khi resolver vi phạm nullability.
- Phân biệt kết quả không có dữ liệu với lỗi thực thi GraphQL.
- Xử lý null, Mono.empty() và collection rỗng trong Spring for GraphQL.
- Chọn cách biểu diễn phù hợp cho trường hợp không tìm thấy dữ liệu.
- Kiểm thử null result và error propagation bằng GraphQlTester.

## Mapping null result là gì?

Khi GraphQL thực thi một field, resolver có thể trả về một giá trị, một object, một danh sách hoặc không có giá trị. Với field nullable, kết quả không có giá trị được biểu diễn bằng null trong response.

Ví dụ schema:

~~~graphql
type Query {
  bookById(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
}
~~~

Resolver có thể trả null nếu không tìm thấy sách:

~~~java
@QueryMapping
public Book bookById(@Argument("id") String id) {
    return bookService.findById(id).orElse(null);
}
~~~

Nếu sách không tồn tại, response có thể là:

~~~json
{
  "data": {
    "bookById": null
  }
}
~~~

Đây là kết quả hợp lệ vì field bookById có kiểu Book, không có dấu !. GraphQL cho phép field này trả object hoặc null. Nếu resolver chủ động trả null và không phát sinh lỗi, response không cần có mục errors.

Null là một phần của contract GraphQL. Nó không tự động có nghĩa server gặp lỗi. Ý nghĩa của null cần được xác định theo schema và nghiệp vụ: không tìm thấy tài nguyên, dữ liệu tùy chọn chưa được cung cấp, quan hệ không tồn tại hoặc giá trị không thể hiển thị.

## Nullability trong SDL quyết định kết quả hợp lệ

Dấu ! trong SDL đánh dấu một kiểu non-null. Khi không có dấu này, kiểu được phép nhận null.

~~~graphql
type Query {
  optionalBook(id: ID!): Book
  requiredBook(id: ID!): Book!
}
~~~

optionalBook có thể trả một Book hoặc null. requiredBook phải trả về một object khác null. Nếu resolver của requiredBook trả null, GraphQL không thể tạo response phù hợp với schema và phải phát sinh execution error.

Nullability áp dụng cho cả scalar, object và list. Với list, cần phân biệt nullability của list với nullability của từng phần tử:

| SDL | List có thể null? | Phần tử có thể null? |
| --- | --- | --- |
| [Book] | Có | Có |
| [Book!] | Có | Không |
| [Book]! | Không | Có |
| [Book!]! | Không | Không |

Ví dụ:

~~~graphql
type Query {
  books: [Book!]!
}
~~~

Field books phải trả về một list khác null, và từng phần tử trong list cũng phải khác null. List rỗng [] vẫn hợp lệ vì list tồn tại và không có phần tử nào vi phạm nullability.

## Phân biệt null, list rỗng và object rỗng

Ba kết quả này có ý nghĩa khác nhau:

~~~json
{
  "data": {
    "books": null
  }
}
~~~

books: null nghĩa là field không có giá trị. Điều này chỉ hợp lệ nếu kiểu list của field nullable hoặc null xuất hiện do error propagation đến một nullable boundary.

~~~json
{
  "data": {
    "books": []
  }
}
~~~

books: [] nghĩa là truy vấn thành công và không có phần tử nào. Đây thường là kết quả phù hợp cho một query collection không tìm thấy bản ghi.

~~~json
{
  "data": {
    "books": [
      {
        "id": "book-101",
        "title": "Spring GraphQL"
      }
    ]
  }
}
~~~

Object có dữ liệu là kết quả bình thường. Một object có các field nullable đều là null vẫn khác với chính object null: object vẫn tồn tại, nhưng các thuộc tính được chọn không có giá trị.

Trong Java, hãy chuẩn hóa kết quả collection không có phần tử thành list rỗng:

~~~java
@QueryMapping
public List<Book> books() {
    return bookService.findAll();
}
~~~

Nếu service có thể trả null cho collection, nên sửa service hoặc chuẩn hóa tại ranh giới resolver để tránh vô tình trả null cho field [Book!]!. Không dùng null để thay thế cho collection rỗng nếu semantics của API là không có phần tử.

## Null propagation khi field non-null trả null

GraphQL không thể giữ null ở một field được khai báo non-null. Khi resolver trả null cho field đó, GraphQL tạo một execution error và lan truyền null lên field cha gần nhất có thể nhận null.

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

type Author {
  id: ID!
  name: String!
}
~~~

Nếu resolver Book.title trả null, field title vi phạm String!. Vì Book là nullable trong Query.book, toàn bộ object book trở thành null. Các field khác của object đó không còn được trả về như một object hoàn chỉnh.

Response có thể có dạng:

~~~json
{
  "data": {
    "book": null
  },
  "errors": [
    {
      "message": "Cannot return null for non-nullable field Book.title.",
      "path": ["book", "title"]
    }
  ]
}
~~~

Nếu Query.book cũng được khai báo Book!, lỗi tiếp tục lan lên root data:

~~~graphql
type Query {
  book(id: ID!): Book!
}
~~~

Khi đó response có thể là:

~~~json
{
  "data": null,
  "errors": [
    {
      "message": "Cannot return null for non-nullable field Book.title.",
      "path": ["book", "title"]
    }
  ]
}
~~~

Quy tắc này gọi là null propagation hoặc error propagation. Nó bảo đảm response không chứa null ở nơi schema cam kết non-null. Một lỗi ở field con có thể làm mất toàn bộ object cha hoặc một nhánh lớn hơn nếu các field cha cũng non-null.

### Null propagation với list

Xét các khai báo:

~~~graphql
type Query {
  nullableItems: [Book!]
  requiredItems: [Book!]!
}
~~~

Nếu một phần tử của list là null, phần tử đó vi phạm Book!. GraphQL không thể giữ riêng phần tử null trong list. Kết quả của toàn bộ list trở thành null.

- Với nullableItems: [Book!], list được phép null, nên lỗi dừng ở field nullableItems.
- Với requiredItems: [Book!]!, list cũng non-null, nên lỗi tiếp tục lan lên field cha.

Ngược lại, với [Book], phần tử có thể null. Một phần tử null không tự tạo lỗi nullability.

Hãy chọn nullability dựa trên khả năng bảo đảm dữ liệu. Nếu một phần tử trong collection có thể thiếu hợp lệ, [Book] có thể phản ánh đúng contract. Nếu mọi phần tử bắt buộc phải có, [Book!] phù hợp hơn và server cần xử lý dữ liệu thiếu trước khi trả list.

## Null result khác với execution error

Resolver có thể trả null theo chủ đích hoặc phát sinh exception. Hai tình huống này có response khác nhau:

| Tình huống | Field nullable | errors |
| --- | --- | --- |
| Resolver trả null trực tiếp | Giá trị field là null | Không có lỗi nếu không có lỗi khác |
| Resolver trả null cho field non-null | null lan truyền lên nullable boundary | Có execution error |
| Resolver ném exception | Field thường trở thành null, sau đó áp dụng null propagation theo schema | Có execution error |
| Input không hợp lệ trước khi resolver chạy | Operation bị từ chối hoặc không thực thi phần tương ứng | Có lỗi validation/coercion |

Ví dụ, không tìm thấy sách có thể là kết quả bình thường của một query lookup. Nếu schema cho phép Book nullable, trả null có thể là lựa chọn phù hợp.

Ngược lại, database không khả dụng là lỗi hạ tầng. Không nên âm thầm chuyển lỗi này thành null nếu client cần biết request thất bại. Hãy ném exception và ánh xạ thành GraphQL error theo chính sách của API.

Không dùng null để che giấu mọi lỗi. Nếu server trả null cho một field nullable khi có sự cố, client không thể phân biệt không có dữ liệu với không lấy được dữ liệu trừ khi API cung cấp thêm thông tin lỗi.

## Chọn semantics khi không tìm thấy dữ liệu

Không có một quy tắc bắt buộc rằng mọi query không tìm thấy đều phải trả null hoặc error. Hãy chọn theo ý nghĩa của field:

| Use case | Cách biểu diễn thường phù hợp |
| --- | --- |
| Tìm một tài nguyên có thể không tồn tại | Field object nullable; trả null khi không tìm thấy |
| Tìm danh sách không có phần tử phù hợp | Trả list rỗng [] |
| Đọc một field tùy chọn chưa có dữ liệu | Field nullable; trả null |
| Tài nguyên bắt buộc theo invariant nhưng bị thiếu do dữ liệu hỏng | Phát sinh lỗi để không che giấu vi phạm |
| Người dùng không có quyền truy cập | Áp dụng chính sách authorization; có thể trả lỗi hoặc che giấu sự tồn tại tùy yêu cầu bảo mật |
| Dịch vụ phụ thuộc tạm thời không hoạt động | Trả GraphQL error theo chính sách lỗi, không giả vờ rằng dữ liệu đơn giản là vắng mặt |

Ví dụ query tìm sách:

~~~graphql
type Query {
  bookById(id: ID!): Book
  booksByAuthor(authorId: ID!): [Book!]!
}
~~~

Với bookById, không tìm thấy một sách có thể trả null. Với booksByAuthor, không có sách của tác giả đó thường nên trả []. Hai field có semantics khác nhau dù cùng đọc dữ liệu từ một miền nghiệp vụ.

## Mapping null trong annotated controller

Với method trả object đồng bộ, Java null trở thành kết quả null của field:

~~~java
@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book bookById(@Argument("id") String id) {
        return bookService.findById(id).orElse(null);
    }
}
~~~

Schema cần cho phép null:

~~~graphql
type Query {
  bookById(id: ID!): Book
}
~~~

Nếu muốn field luôn có kết quả, không chỉ đổi schema thành Book! rồi giữ nguyên orElse(null). Cần bảo đảm service luôn trả object hoặc ném exception có ý nghĩa:

~~~java
@QueryMapping
public Book requiredBook(@Argument("id") String id) {
    return bookService.findById(id)
            .orElseThrow(() -> new BookNotFoundException(id));
}
~~~

Exception có thể được xử lý bởi DataFetcherExceptionResolver hoặc cơ chế exception handler của Spring for GraphQL. Cách ánh xạ lỗi cần thống nhất với error contract của API. Dù field là non-null, exception vẫn tạo GraphQL error; null propagation tiếp tục theo schema.

## Mapping null với Mono và Flux

Spring for GraphQL hỗ trợ reactive return types. Khi resolver trả Mono<T>, kết quả có thể phát ra một giá trị hoặc hoàn tất mà không phát giá trị.

### Mono.empty() tương ứng với không có giá trị

Ví dụ service trả Mono<Book>:

~~~java
@QueryMapping
public Mono<Book> bookById(@Argument("id") String id) {
    return bookService.findById(id);
}
~~~

Nếu service trả Mono.empty(), resolver không có object để cung cấp. Kết quả field được xem như null, vì vậy schema nên khai báo field nullable nếu không tìm thấy là kết quả hợp lệ:

~~~graphql
type Query {
  bookById(id: ID!): Book
}
~~~

Nếu schema khai báo Book!, Mono.empty() dẫn đến vi phạm non-null khi GraphQL xử lý kết quả. Đừng dùng empty publisher cho field non-null nếu không có giá trị thay thế hợp lệ.

Nếu cần phân biệt không tìm thấy với lỗi truy cập dữ liệu, hãy để service phát sinh error signal cho lỗi thực sự. Không chuyển mọi exception thành Mono.empty() vì điều đó làm mất thông tin lỗi.

### Flux.empty() và list rỗng

Với query thông thường trả về collection, Flux<T> được thu thập thành một danh sách kết quả. Một Flux.empty() vì thế tương ứng với list rỗng, không phải list null:

~~~java
@QueryMapping
public Flux<Book> booksByAuthor(
        @Argument("authorId") String authorId) {
    return bookService.findByAuthorId(authorId);
}
~~~

Schema:

~~~graphql
type Query {
  booksByAuthor(authorId: ID!): [Book!]!
}
~~~

Nếu không có sách, Flux hoàn tất mà không phát phần tử và kết quả collection là [], phù hợp với [Book!]!.

Đừng nhầm trường hợp này với Mono.empty() của một object. Mono.empty() biểu diễn không có một giá trị đơn; Flux.empty() trong query collection biểu diễn một tập kết quả không có phần tử.

### Flux trong subscription

Với subscription, Flux<T> là luồng các sự kiện phát theo thời gian. Nếu stream hoàn tất, subscription kết thúc; nó không có nghĩa là một query list trả về null.

~~~graphql
type Subscription {
  bookAdded: Book!
}
~~~

~~~java
@SubscriptionMapping
public Flux<Book> bookAdded() {
    return bookEventService.bookAdded();
}
~~~

Mỗi phần tử phát ra là một payload subscription riêng. Nếu nguồn sự kiện phát một giá trị null cho field Book!, kết quả đó vi phạm non-null. Nguồn sự kiện nên chỉ phát payload hợp lệ và xử lý lỗi stream theo chính sách đã định.

## Null ở field lồng nhau

Nullability của field lồng nhau quyết định phạm vi dữ liệu bị ảnh hưởng:

~~~graphql
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
}
~~~

Nếu Book.author nullable và resolver trả null, response vẫn có thể giữ object Book:

~~~json
{
  "data": {
    "book": {
      "id": "book-101",
      "title": "Spring GraphQL",
      "author": null
    }
  }
}
~~~

Nếu đổi field thành author: Author!, null từ resolver làm toàn bộ Book trở thành null vì book là nullable. Nếu book: Book!, lỗi tiếp tục lan lên data.

Điều này đặc biệt quan trọng khi một field lồng nhau gọi service khác. Một tác giả không tồn tại có thể là trạng thái hợp lệ nếu quan hệ tùy chọn; nếu schema đánh dấu Author!, server phải bảo đảm quan hệ luôn có và resolver không thể trả null.

## Null và bảo mật

Có trường hợp API cố ý không tiết lộ tài nguyên có tồn tại hay không. Ví dụ, người dùng không có quyền xem một đơn hàng. Tùy chính sách bảo mật, server có thể trả null cho field nullable để không phân biệt không tồn tại và không được phép xem, hoặc trả GraphQL error với mã phù hợp.

Quyết định này cần nhất quán và được áp dụng ở mọi đường truy cập. Không được chỉ dựa vào việc trả null để bảo vệ dữ liệu: resolver vẫn phải kiểm tra quyền trước khi trả object hoặc field nhạy cảm. Một client có thể truy vấn cùng object thông qua field khác nếu server không bảo vệ đầy đủ.

Nếu chọn trả null để che giấu sự tồn tại, hãy cân nhắc logging và monitoring phía server để đội vận hành vẫn phân biệt được truy cập bị từ chối với tài nguyên không tồn tại. Không đưa thông tin nhạy cảm vào GraphQL error message.

## Kiểm thử null result bằng GraphQlTester

GraphQlTester cho phép kiểm tra một field trả null mà không có lỗi:

~~~java
graphQlTester.document("""
        query BookById($id: ID!) {
            bookById(id: $id) {
                id
            }
        }
        """)
    .variable("id", "missing-book")
    .execute()
    .path("bookById")
    .valueIsNull();
~~~

Để kiểm tra field non-null vi phạm nullability, hãy xác minh cả GraphQL error và đường dẫn field:

~~~java
graphQlTester.document("""
        query {
            requiredBook(id: "missing-book") {
                id
            }
        }
        """)
    .execute()
    .errors()
    .satisfy(errors -> {
        // Xác minh có execution error tại field requiredBook.
    });
~~~

Trong test đầy đủ, nên kiểm tra thêm response path hoặc error classification phù hợp với cách API ánh xạ exception. Không nên chỉ xác nhận có bất kỳ lỗi nào, vì lỗi cú pháp hoặc lỗi setup cũng có thể làm test pass sai mục đích.

Nên có test cho:

1. Nullable object resolver trả null và response có field null, không có errors.
2. Non-null object resolver trả null và response có execution error.
3. Field con nullable trả null nhưng object cha vẫn tồn tại.
4. Field con non-null trả null và lỗi lan truyền lên nullable boundary.
5. List rỗng trả [].
6. List có phần tử null vi phạm [Book!] và gây null propagation.
7. Mono.empty() với field nullable và non-null.
8. Flux.empty() với field list.
9. Exception từ service được ánh xạ thành error đúng contract.
10. Field nhạy cảm vẫn được kiểm tra quyền dù response có thể trả null.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Field trả null mà client tưởng server lỗi | Contract chưa mô tả rõ ý nghĩa null | Xác định semantics và tài liệu hóa field nullable |
| Cannot return null for non-nullable field | Resolver hoặc nguồn dữ liệu trả null cho field có dấu ! | Sửa dữ liệu/logic hoặc thay đổi nullability nếu contract cho phép |
| Cả object cha biến thành null | Field con non-null trả null và null propagation lan lên | Xem lại nullability từng cấp và error path |
| Query collection trả null khi không có bản ghi | Service trả null thay vì collection rỗng | Trả List.of() hoặc Flux.empty() phù hợp |
| Mono.empty() gây lỗi | Field schema non-null nhưng publisher không phát giá trị | Dùng field nullable hoặc phát giá trị hợp lệ |
| Mọi lỗi service đều biến thành null | Exception bị chuyển thành empty/null quá sớm | Giữ error signal và ánh xạ GraphQL error |
| List có phần tử null làm hỏng cả list | Phần tử vi phạm Book! trong list | Làm sạch dữ liệu hoặc thay đổi nullability đúng semantics |
| Dữ liệu nhạy cảm bị lộ qua field khác | Chỉ ẩn field ở client hoặc một resolver | Áp dụng authorization ở server cho mọi đường truy cập |

## Thực hành tổng hợp

Xây dựng API thư viện với các field:

1. bookById(id: ID!): Book trả null khi không tìm thấy sách.
2. requiredBook(id: ID!): Book! phát sinh lỗi nghiệp vụ khi không tìm thấy.
3. booksByAuthor(authorId: ID!): [Book!]! trả list rỗng nếu không có sách.
4. Book.author: Author là quan hệ tùy chọn và có thể trả null.
5. Thử đổi Book.author thành Author! để quan sát null propagation.
6. Chuyển bookById sang Mono<Book> và kiểm tra Mono.empty().
7. Chuyển booksByAuthor sang Flux<Book> và kiểm tra Flux.empty().
8. Viết GraphQlTester test cho null result, execution error, list rỗng và field con non-null.

Sau bài thực hành, hãy mô tả response cho từng trường hợp và chỉ ra null boundary nơi lỗi dừng lại. Giải thích vì sao không nên chuyển lỗi database thành Mono.empty() và vì sao list không có phần tử thường nên trả [].

## Ghi nhớ

Kết quả null là một phần của GraphQL contract. Field nullable có thể trả null mà không tạo error; field non-null trả null sẽ tạo execution error và lan truyền null lên nullable boundary gần nhất. Với list, cần phân biệt null list, list rỗng và phần tử null. Trong Spring for GraphQL, Java null và Mono.empty() biểu diễn không có một giá trị đơn; Flux.empty() trong query collection tạo list rỗng, còn Flux của subscription là stream sự kiện. Hãy chọn nullability theo invariant dữ liệu, phân biệt không tìm thấy với lỗi hệ thống, bảo vệ field ở server và kiểm thử cả response lẫn errors bằng GraphQlTester.
