# Object type

Trong module SPRING_GRAPHQL, người học xây dựng GraphQL API với Spring for GraphQL bằng cách định nghĩa schema SDL, triển khai resolver và kết nối các field với service. **Object type** là thành phần trung tâm của schema: nó mô tả một đối tượng mà client có thể truy vấn, gồm tên kiểu và tập hợp field có kiểu dữ liệu cụ thể.

Ví dụ, một hệ thống quản lý sách có thể công bố các object type Book, Author và Review. Một quyển sách có mã, tiêu đề, tác giả và danh sách đánh giá. Thông qua các field liên kết, client có thể truy vấn sách cùng những thông tin liên quan trong một operation. Object type mô tả hình dạng dữ liệu của API; nó không bắt buộc phải trùng với entity, bảng cơ sở dữ liệu hoặc cấu trúc nội bộ của ứng dụng.

## Khai báo object type bằng SDL

Trong GraphQL Schema Definition Language (SDL), từ khóa **type** dùng để khai báo một object type. Bên trong cặp ngoặc nhọn là danh sách field:

~~~graphql
type Book {
  id: ID!
  title: String!
  subtitle: String
  author: Author!
  reviews(first: Int = 10): [Review!]!
}

type Author {
  id: ID!
  name: String!
  books: [Book!]!
}

type Review {
  id: ID!
  rating: Int!
  comment: String
}
~~~

Khai báo trên tạo ra ba object type:

- **Book** mô tả một quyển sách. Field id và title bắt buộc có giá trị; subtitle có thể là null.
- **Author** mô tả tác giả. Field books liên kết tới danh sách sách của tác giả.
- **Review** mô tả một đánh giá. rating là số nguyên bắt buộc, còn comment là nội dung tùy chọn.

Mỗi object type phải có ít nhất một field. Tên kiểu thường viết theo PascalCase như Book hoặc Author; tên field thường viết theo camelCase như publishedAt hoặc authorId. Đây là quy ước đặt tên phổ biến giúp schema nhất quán và dễ đọc.

Field là đơn vị dữ liệu mà client có thể chọn trong selection set. Một field có tên và kiểu trả về; field cũng có thể nhận argument để lọc, phân trang hoặc điều khiển cách lấy dữ liệu. Trong ví dụ, reviews nhận argument first và dùng giá trị mặc định 10 khi client không truyền argument này.

## Object type là kiểu đầu ra

Object type thuộc nhóm output type. Nó có thể xuất hiện làm kiểu trả về của field trong Query, Mutation, Subscription hoặc một field lồng nhau. Kiểu trả về của field có thể là scalar, enum, object, interface hoặc union; các kiểu này cũng có thể được bọc bằng list và non-null.

Ví dụ:

~~~graphql
type Query {
  book(id: ID!): Book
  books(authorId: ID): [Book!]!
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
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

input CreateBookInput {
  title: String!
  authorId: ID!
}
~~~

Trong schema này, Query và Mutation cũng chính là object type. GraphQL yêu cầu schema có root operation type Query; các root type Mutation và Subscription được khai báo khi API cần thao tác ghi hoặc phát sự kiện. Field book trả về một Book có thể không tồn tại nên kiểu Book không có dấu !. Field createBook trả về Book! vì hợp đồng quy định kết quả không được null.

Object type không dùng làm kiểu dữ liệu đầu vào cho argument. Nếu cần nhận một nhóm giá trị từ client, hãy khai báo **input object type** bằng từ khóa input, như CreateBookInput ở ví dụ trên. Input object chỉ chứa các kiểu đầu vào hợp lệ như scalar, enum hoặc input object khác, có thể kết hợp với list và non-null wrapper; nó không thể chứa field có kiểu Book hay Author. Quy tắc này tách biệt cấu trúc dữ liệu mà client gửi lên khỏi cấu trúc dữ liệu server trả về.

## Field có thể chứa scalar hoặc object khác

Một object type thường kết hợp nhiều loại field:

| Kiểu field | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Scalar | id: ID!, title: String! | Giá trị đơn như chuỗi, số hoặc boolean |
| Enum | status: BookStatus! | Một giá trị trong tập lựa chọn được định nghĩa trước |
| Object | author: Author | Một object lồng bên trong object hiện tại |
| List | reviews: [Review!]! | Danh sách các object hoặc giá trị |
| Field có argument | reviews(first: Int = 10): [Review!]! | Field nhận tham số để điều khiển dữ liệu trả về |

Ví dụ enum:

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

Enum giới hạn giá trị hợp lệ theo danh sách đã khai báo. Khi object type dùng enum, client biết trước những trạng thái có thể nhận và có thể dùng chúng trong biến hoặc argument phù hợp.

Field kiểu object tạo quan hệ giữa các kiểu. Ví dụ Book.author trả về Author, còn Author.books trả về danh sách Book. Những quan hệ này cho phép client đi từ một object sang object liên quan theo schema. Một quan hệ có thể một-một, một-nhiều hoặc nhiều-nhiều tùy mô hình nghiệp vụ; SDL biểu diễn hình dạng và cardinality của kết quả, còn resolver chịu trách nhiệm tải dữ liệu thực tế.

## List và non-null trong object field

GraphQL dùng dấu ngoặc vuông để biểu diễn danh sách và dấu chấm than để biểu diễn giá trị không được null. Hai dấu này có thể kết hợp, vì vậy cần đọc đúng vị trí của chúng:

| Kiểu | Danh sách có thể null? | Phần tử có thể null? |
| --- | --- | --- |
| [Book] | Có | Có |
| [Book!] | Có | Không |
| [Book]! | Không | Có |
| [Book!]! | Không | Không |

Ví dụ:

~~~graphql
type Author {
  biography: String
  books: [Book!]!
}
~~~

biography có thể không có nội dung. Ngược lại, books luôn phải trả về một danh sách; danh sách rỗng là hợp lệ, nhưng bản thân danh sách không được null và không được có phần tử null.

Nullability là một phần của hợp đồng API và ảnh hưởng tới cách GraphQL xử lý lỗi. Nếu resolver của field nullable trả về null, client nhận null ở field đó. Nếu resolver của field non-null trả về null hoặc phát sinh lỗi khiến field không thể tạo giá trị, GraphQL ghi nhận lỗi và đẩy null lên field cha gần nhất có thể nhận null. Quá trình này được gọi là null propagation. Nếu nhiều cấp cha cũng non-null, null tiếp tục lan lên cho tới vị trí nullable; vì vậy một field non-null sâu bên trong có thể khiến một phần lớn hơn của response trở thành null.

Khi chọn dấu !, hãy dựa trên quy tắc nghiệp vụ và khả năng dữ liệu thực tế. Chỉ đánh dấu non-null khi ứng dụng có thể bảo đảm field luôn có giá trị trong mọi trường hợp hợp lệ. Nếu tác giả có thể bị xóa hoặc không xác định, field author nên được khai báo nullable hoặc ứng dụng cần bảo đảm một giá trị thay thế hợp lệ.

## Truy vấn object lồng nhau

Client không nhận toàn bộ field của object một cách mặc định. Client gửi selection set để chọn những field cần thiết. Nếu field trả về một object khác, client mở một selection set lồng nhau để mô tả những field muốn đọc từ object đó.

~~~graphql
query FindBook($id: ID!) {
  book(id: $id) {
    id
    title
    author {
      id
      name
      books {
        id
        title
      }
    }
    reviews(first: 3) {
      id
      rating
      comment
    }
  }
}
~~~

Operation này yêu cầu một quyển sách, thông tin tác giả, danh sách sách của tác giả và ba đánh giá đầu tiên. Response có cấu trúc tương ứng với selection set:

~~~json
{
  "data": {
    "book": {
      "id": "book-101",
      "title": "Spring in Action",
      "author": {
        "id": "author-12",
        "name": "Craig Walls",
        "books": [
          {
            "id": "book-101",
            "title": "Spring in Action"
          }
        ]
      },
      "reviews": [
        {
          "id": "review-1",
          "rating": 5,
          "comment": "Useful examples"
        }
      ]
    }
  }
}
~~~

Schema có thể mô tả quan hệ vòng như Book.author và Author.books cùng tham chiếu lẫn nhau. Điều đó không tạo ra vòng lặp vô hạn trong response, vì client phải chỉ rõ selection set cho mỗi operation và operation có độ sâu hữu hạn. Server vẫn cần giới hạn độ sâu hoặc độ phức tạp truy vấn để tránh operation quá lớn.

## Argument của object field

Argument thuộc về field, không thuộc về toàn bộ object type. Chúng cho phép client truyền điều kiện lọc, thứ tự, phân trang hoặc các tùy chọn nghiệp vụ:

~~~graphql
type Book {
  id: ID!
  title: String!
  reviews(first: Int = 10, minRating: Int): [Review!]!
}
~~~

Client có thể gọi field reviews với các giá trị khác nhau:

~~~graphql
query {
  book(id: "book-101") {
    title
    recentReviews: reviews(first: 5, minRating: 4) {
      id
      rating
    }
  }
}
~~~

Alias recentReviews đặt tên khác cho field trong response. Argument first yêu cầu tối đa năm kết quả, còn minRating lọc theo điểm đánh giá. Giá trị mặc định của first được sử dụng khi client bỏ qua argument; nếu client truyền null tường minh, hành vi phụ thuộc vào nullability và cách resolver xử lý.

Với danh sách lớn, nên thiết kế phân trang rõ ràng thay vì để client tải không giới hạn. Có thể dùng limit/offset hoặc cursor tùy yêu cầu nhất quán dữ liệu và cách truy cập nguồn dữ liệu. Schema cần mô tả rõ ý nghĩa của các argument và giới hạn tối đa mà server chấp nhận.

## Spring for GraphQL ánh xạ object field vào Java

SDL mô tả hợp đồng, còn resolver cung cấp giá trị cho các field. Spring for GraphQL hỗ trợ khai báo resolver bằng annotation trên bean được đánh dấu @Controller. Root field thuộc Query có thể dùng @QueryMapping; field của object type có thể dùng @SchemaMapping.

Ví dụ schema:

~~~graphql
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
~~~

Java model và controller:

~~~java
public record Book(String id, String title, String authorId) {
}

public record Author(String id, String name) {
}
~~~

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
    public Mono<Book> book(@Argument String id) {
        return bookService.findById(id);
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Mono<Author> author(Book book) {
        return authorService.findById(book.authorId());
    }
}
~~~

Phương thức book ánh xạ field book của root type Query. Phương thức author ánh xạ field author của object type Book. Tham số Book book là source object: nó chứa kết quả đã được resolver cha trả về. Spring for GraphQL truyền source object này cho resolver field con, sau đó resolver đọc authorId và gọi service lấy tác giả.

Nếu Java object đã có thuộc tính trùng với tên field trong schema, GraphQL có thể dùng cơ chế property access mặc định để lấy giá trị mà không cần viết resolver riêng. Ví dụ record Book có accessor id() và title(), nên các field id và title có thể được đọc trực tiếp. Khi field cần gọi service, áp dụng quy tắc nghiệp vụ, hoặc lấy dữ liệu từ một nguồn khác, hãy viết resolver rõ ràng bằng @SchemaMapping.

Object field cũng có thể nhận argument. Ví dụ field reviews(first: Int) có thể ánh xạ tới phương thức:

~~~java
@SchemaMapping(typeName = "Book", field = "reviews")
public Flux<Review> reviews(Book book, @Argument Integer first) {
    return reviewService.findByBookId(book.id(), first);
}
~~~

Tham số Book là source object; tham số first nhận argument của field. Tách source object và argument giúp resolver biết cả object cha đang được phân giải lẫn tùy chọn do client gửi.

## Object type và vấn đề N+1

Object field lồng nhau rất tiện cho client, nhưng có thể tạo nhiều lần truy cập dữ liệu nếu mỗi resolver con tự gọi database hoặc service. Ví dụ query lấy 100 quyển sách và chọn author có thể khiến resolver author chạy 100 lần. Đây là vấn đề N+1.

Spring for GraphQL hỗ trợ @BatchMapping và DataLoader để gom các lần tải dữ liệu. Thay vì truy vấn tác giả cho từng quyển sách, batch resolver nhận một nhóm Book rồi tải tác giả theo danh sách authorId. Tầng repository hoặc service cần có thao tác tải theo lô thực sự; chỉ gom các lần gọi vào một phương thức mà bên trong vẫn gọi database từng lần thì chưa giải quyết được N+1.

Ngoài batching, nên phân trang danh sách, giới hạn độ sâu và độ phức tạp của operation, đặt timeout và theo dõi thời gian thực thi của từng resolver. Một object type có thể liên kết nhiều object khác, nhưng schema tốt cần phản ánh nhu cầu nghiệp vụ và có giới hạn vận hành hợp lý.

## Object type kết hợp interface và union

Object type có thể triển khai một interface để chia sẻ tập field chung:

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

Book và Author là các object type cụ thể. Cả hai đều cung cấp field id theo hợp đồng của Node, đồng thời có thể bổ sung field riêng. Interface hữu ích khi nhiều kiểu object có một nhóm field chung.

Union biểu diễn một giá trị có thể thuộc một trong nhiều object type mà không yêu cầu chúng có chung field:

~~~graphql
union SearchResult = Book | Author

type Query {
  search(text: String!): [SearchResult!]!
}
~~~

Khi client truy vấn field của một kiểu cụ thể trong union, client dùng inline fragment:

~~~graphql
query Search {
  search(text: "Spring") {
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

Các cơ chế interface và union mở rộng khả năng biểu diễn object trong schema. Khi dùng chúng, resolver cần trả về đúng object type cụ thể để GraphQL xác định các field tương ứng.

## Nguyên tắc thiết kế object type

Khi thiết kế object type cho GraphQL API, hãy bắt đầu từ dữ liệu và hành vi mà client cần, sau đó quyết định field và quan hệ phù hợp:

1. **Đặt tên theo khái niệm nghiệp vụ.** Book, Author hoặc Order dễ hiểu hơn những tên phản ánh chi tiết bảng hay lớp persistence.
2. **Chỉ công bố field có chủ đích.** Không đưa mật khẩu, token, cờ nội bộ hoặc dữ liệu nhạy cảm vào schema chỉ vì chúng tồn tại trong Java entity.
3. **Chọn nullability theo dữ liệu thực tế.** Dùng dấu ! khi ứng dụng có thể bảo đảm giá trị; cân nhắc tác động của null propagation khi field lỗi.
4. **Thiết kế danh sách có phân trang.** Tránh field trả về số lượng bản ghi không giới hạn.
5. **Dùng input object cho dữ liệu đầu vào.** Không tái sử dụng output object làm input; hai cấu trúc có mục đích và quy tắc khác nhau.
6. **Theo dõi chi phí của quan hệ lồng nhau.** Dùng batch loading khi nhiều object cùng cần một loại dữ liệu liên quan.
7. **Giữ schema ổn định và có khả năng tiến hóa.** Khi ngừng hỗ trợ field, có thể đánh dấu deprecated và cho client thời gian chuyển đổi trước khi xóa.

Object type là cách GraphQL mô tả các thực thể và quan hệ mà API công bố. Khi kết hợp field, argument, list và nullability đúng cách, schema trở thành hợp đồng rõ ràng cho client. Trong Spring for GraphQL, @QueryMapping và @SchemaMapping nối hợp đồng đó với Java resolver; service và repository chịu trách nhiệm lấy dữ liệu, còn DataLoader hoặc @BatchMapping giúp kiểm soát chi phí khi object có nhiều quan hệ.
