# Object type

Object type là kiểu dữ liệu cốt lõi dùng để mô tả một đối tượng mà GraphQL API có thể trả về cho client. Mỗi object type định nghĩa một tập field có tên, kiểu trả về và có thể có các argument. Khi client truy vấn một field trả về object type, client tiếp tục chọn những field con mà mình cần.

Trong Spring for GraphQL, object type thường được khai báo bằng SDL, còn giá trị của từng field được cung cấp bởi data fetcher hoặc resolver. Spring hỗ trợ ánh xạ method Java vào field bằng các annotation như **@QueryMapping** và **@SchemaMapping**. Với các field có thể lấy trực tiếp từ property của source object, GraphQL Java còn có thể dùng property data fetcher mặc định.

Bài này tập trung vào cách thiết kế object type, cách field tạo thành cấu trúc dữ liệu lồng nhau, cách argument hoạt động, mối quan hệ giữa object type và Java class, cũng như cách triển khai resolver trong Spring for GraphQL.

## 1. Object type mô tả hình dạng dữ liệu đầu ra

Một object type được khai báo bằng từ khóa **type** trong SDL:

~~~graphql
type Book {
  id: ID!
  title: String!
  publishedAt: String
}
~~~

Khai báo trên tạo một object type có tên **Book** với ba field:

- **id** có kiểu **ID!**, nghĩa là giá trị trả về bắt buộc khác null.
- **title** có kiểu **String!**, nghĩa là tiêu đề luôn phải có giá trị.
- **publishedAt** có kiểu **String**, nghĩa là giá trị có thể là null.

Object type định nghĩa hợp đồng mà client được phép đọc. Nó không phải là một instance cụ thể, không phải câu lệnh truy vấn cơ sở dữ liệu và cũng không tự tạo ra một Java object. Server cần có logic để cung cấp giá trị cho các field khi operation được thực thi.

Có thể xem object type là một mô tả cấu trúc:

~~~mermaid
classDiagram
    class Book {
        ID id
        String title
        String publishedAt
    }
~~~

Sơ đồ này chỉ minh họa các field trong schema. Kiểu GraphQL và kiểu Java có thể được ánh xạ với nhau, nhưng không bắt buộc có cấu trúc hoặc tên giống hệt nhau.

## 2. Field của object type

Mỗi field trong object type có một tên và một kiểu đầu ra. Cú pháp tổng quát:

~~~graphql
type TypeName {
  fieldName: OutputType
}
~~~

Một object type có thể chứa nhiều nhóm output type:

- Scalar như **String**, **Int**, **Float**, **Boolean** và **ID**.
- Enum như **BookStatus**.
- Object type khác như **Author** hoặc **Review**.
- Interface hoặc union khi field có thể trả về một trong nhiều object type.
- Các kiểu bọc list và non-null như **[Book!]!**.

Ví dụ:

~~~graphql
enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

type Book {
  id: ID!
  title: String!
  price: Float!
  status: BookStatus!
  tags: [String!]!
  publisher: Publisher
}

type Publisher {
  id: ID!
  name: String!
}
~~~

Trong ví dụ, **Book** có các field scalar, enum, list và quan hệ tới một object type khác. Field **publisher** nullable vì sách có thể chưa được gán nhà xuất bản. Field **tags** luôn trả về một danh sách và từng phần tử trong danh sách phải khác null.

### Tên field và quy ước đặt tên

GraphQL phân biệt chữ hoa và chữ thường. Theo quy ước phổ biến:

- Object type dùng PascalCase, ví dụ **Book**, **BookReview**.
- Field dùng camelCase, ví dụ **publishedAt**, **averageRating**.
- Tên field nên diễn đạt dữ liệu hoặc hành động một cách rõ ràng.
- Tránh tên quá chung chung như **value**, **data** hoặc **info** nếu không có ngữ cảnh cụ thể.
- Không tự đặt tên type hoặc field bắt đầu bằng hai dấu gạch dưới; tiền tố này được dành cho hệ thống introspection của GraphQL, chẳng hạn meta-field **__typename**.

Object type cũng có thể triển khai một hoặc nhiều interface và có thể là thành viên của union. Khi triển khai interface, object phải cung cấp các field mà interface yêu cầu với kiểu tương thích:

~~~graphql
interface Node {
  id: ID!
}

type Book implements Node {
  id: ID!
  title: String!
}
~~~

Trong ví dụ, **Book** vẫn là một object type cụ thể; **Node** chỉ mô tả hợp đồng field dùng chung.

Không nên đổi tên field công khai tùy tiện sau khi client đã sử dụng API. Đổi tên field tương đương xóa field cũ và thêm field mới, có thể làm operation của client cũ không còn hợp lệ. Khi cần thay thế, có thể thêm field mới, đánh dấu field cũ bằng **@deprecated**, rồi loại bỏ sau giai đoạn chuyển đổi phù hợp.

### Mô tả object và field

SDL hỗ trợ mô tả bằng string literal đặt ngay trước định nghĩa type hoặc field:

~~~graphql
"""
Một đầu sách được cung cấp bởi catalog service.
"""
type Book {
  "Mã định danh duy nhất của sách."
  id: ID!

  "Tiêu đề hiển thị cho người đọc."
  title: String!

  "Thời điểm sách được phát hành."
  publishedAt: String
}
~~~

Mô tả giúp schema dễ khám phá hơn trong GraphiQL, IDE và các công cụ introspection. Hãy viết mô tả về ý nghĩa nghiệp vụ, đơn vị đo, quy tắc null hoặc điều kiện sử dụng khi các chi tiết đó không thể hiện rõ từ tên field.

## 3. Root object types

Các root operation type của GraphQL cũng là object type. Chúng là điểm bắt đầu của mỗi operation:

~~~graphql
type Query {
  book(id: ID!): Book
  books: [Book!]!
}

type Mutation {
  createBook(title: String!): Book!
}

type Subscription {
  bookPublished: Book!
}
~~~

Ở đây:

- **Query** cung cấp các field để đọc dữ liệu.
- **Mutation** cung cấp các field để thay đổi dữ liệu.
- **Subscription** cung cấp các field tạo luồng cập nhật.

Một schema GraphQL phải có root Query. Root Mutation và root Subscription là tùy chọn. Dù là root type hay object type lồng nhau, chúng vẫn tuân theo cùng quy tắc về field và output type.

Client không truy vấn trực tiếp tên type. Client bắt đầu từ một root field rồi chọn các field tiếp theo trong selection set:

~~~graphql
query {
  book(id: "book-01") {
    id
    title
  }
}
~~~

Trong operation trên, **book** là field của **Query**; kết quả của nó có kiểu **Book**. Selection set bên trong chọn hai field của object kết quả.

## 4. Object field có thể nhận argument

Field có thể khai báo argument để client truyền tham số cho việc lấy dữ liệu. Cú pháp:

~~~graphql
type TypeName {
  fieldName(argumentName: InputType): OutputType
}
~~~

Ví dụ:

~~~graphql
type Book {
  id: ID!
  title: String!
  reviews(first: Int = 10): [Review!]!
}

type Review {
  id: ID!
  rating: Int!
  content: String
}
~~~

Field **reviews** nhận argument **first** để giới hạn số đánh giá trả về. Client có thể dùng giá trị mặc định hoặc truyền giá trị khác:

~~~graphql
query {
  book(id: "book-01") {
    title
    reviews(first: 3) {
      rating
      content
    }
  }
}
~~~

Argument có thể có kiểu scalar, enum hoặc input object. Object type, interface và union không phải input type, do đó không thể dùng trực tiếp chúng làm kiểu argument. Nếu cần gửi nhiều tiêu chí lọc, hãy tạo một input object riêng.

Ví dụ:

~~~graphql
enum ReviewSort {
  NEWEST
  HIGHEST_RATING
}

input ReviewFilter {
  minimumRating: Int
  containsText: String
}

type Book {
  id: ID!
  reviews(
    filter: ReviewFilter
    sort: ReviewSort = NEWEST
    first: Int = 10
  ): [Review!]!
}
~~~

Khi thiết kế argument, hãy cân nhắc:

- Giá trị có bắt buộc không, hay có thể để mặc định?
- Giá trị null có ý nghĩa khác với việc không truyền argument không?
- Có cần giới hạn min/max cho số lượng kết quả không?
- Có cần phân trang bằng cursor thay vì chỉ dùng offset hoặc số lượng?
- Các field cùng nhóm có thể dùng chung một input object hay cần input riêng?

GraphQL kiểm tra kiểu và việc truyền argument theo schema, nhưng validation nghiệp vụ như giới hạn **first** tối đa 100 vẫn cần được thực hiện ở server.

## 5. Quan hệ giữa các object type

Object type có thể tham chiếu đến object type khác trong kiểu trả về của field. Nhờ đó, schema mô tả được quan hệ lồng nhau mà client có thể chọn theo nhu cầu.

Ví dụ một catalog có sách, tác giả và nhà xuất bản:

~~~graphql
type Book {
  id: ID!
  title: String!
  author: Author!
  publisher: Publisher
}

type Author {
  id: ID!
  name: String!
  books: [Book!]!
}

type Publisher {
  id: ID!
  name: String!
  books: [Book!]!
}
~~~

Client có thể lấy nhiều cấp dữ liệu trong một operation:

~~~graphql
query {
  book(id: "book-01") {
    id
    title
    author {
      id
      name
    }
    publisher {
      name
    }
  }
}
~~~

GraphQL trả về cấu trúc dữ liệu tương ứng với selection set. Client có thể chỉ chọn **title**, hoặc lấy thêm **author.name** và **publisher.name** mà không cần server tạo một endpoint riêng cho từng tổ hợp field.

Quan hệ trong schema không bắt buộc phản ánh nguyên trạng quan hệ trong database. Ví dụ database có bảng nối giữa sách và tác giả, nhưng schema có thể chỉ công khai một field **author**. Ngược lại, một field như **recommendedBooks** có thể được tổng hợp từ nhiều nguồn dữ liệu mà không tồn tại dưới dạng quan hệ trực tiếp trong database.

### Quan hệ một-một và một-nhiều

Quan hệ một-một hoặc nhiều-một thường được biểu diễn bằng một object field:

~~~graphql
type Book {
  author: Author!
}
~~~

Quan hệ một-nhiều thường được biểu diễn bằng list:

~~~graphql
type Author {
  books: [Book!]!
}
~~~

Schema chỉ thể hiện hình dạng dữ liệu. Nó không bảo đảm resolver tải dữ liệu hiệu quả. Nếu một query lấy 50 tác giả và mỗi tác giả gọi riêng database để lấy sách, server có thể phát sinh N+1 query. Khi đó cần cân nhắc batch loading, DataLoader hoặc **@BatchMapping**.

### Quan hệ đệ quy

Một object type có thể tham chiếu chính nó:

~~~graphql
type Category {
  id: ID!
  name: String!
  parent: Category
  children: [Category!]!
}
~~~

Mô hình này phù hợp với cây danh mục, thư mục, tổ chức hoặc cấu trúc phân cấp. Schema cho phép client truy vấn các cấp lồng nhau:

~~~graphql
query {
  category(id: "root") {
    name
    children {
      name
      children {
        name
      }
    }
  }
}
~~~

Schema đệ quy không có nghĩa operation có thể tự chạy vô hạn. Operation GraphQL là một tài liệu hữu hạn với selection set hữu hạn. Tuy nhiên, client có thể gửi query rất sâu hoặc lặp lại field theo nhiều nhánh khiến chi phí thực thi tăng cao. Server nên áp dụng giới hạn query depth, complexity hoặc các chính sách giới hạn tài nguyên phù hợp.

## 6. Selection set và cách client đọc object

Khi field trả về scalar hoặc enum, client chọn field đó trực tiếp. Khi field trả về object, client phải chỉ rõ selection set của object đó:

~~~graphql
query {
  book(id: "book-01") {
    title
  }
}
~~~

Ví dụ trên hợp lệ vì **title** là scalar field. Nếu client viết:

~~~graphql
query {
  book(id: "book-01")
}
~~~

operation không hợp lệ vì **book** trả về object **Book**, nhưng client không chỉ ra field con cần lấy.

Tương tự, client không thể viết selection set cho scalar:

~~~graphql
query {
  book(id: "book-01") {
    title {
      value
    }
  }
}
~~~

Operation này không hợp lệ vì **title** là **String**, không phải object type.

Quy tắc selection set làm cho GraphQL response có cấu trúc tường minh: mỗi object trong kết quả chỉ chứa những field client yêu cầu. Đây là một đặc điểm quan trọng khi thiết kế object type, vì cấu trúc field chính là bề mặt dữ liệu mà client có thể khám phá và sử dụng.

### Alias và fragment khi truy vấn object

Client có thể dùng alias khi cần lấy cùng một field với argument khác nhau trong một operation:

~~~graphql
query {
  book(id: "book-01") {
    title
    latestReviews: reviews(first: 3) {
      rating
    }
    topReviews: reviews(sort: HIGHEST_RATING, first: 3) {
      rating
    }
  }
}
~~~

Fragment giúp tái sử dụng selection set cho object type:

~~~graphql
fragment BookSummary on Book {
  id
  title
  status
}

query {
  books {
    ...BookSummary
  }
}
~~~

Alias và fragment thuộc ngôn ngữ operation của client; chúng không thay đổi định nghĩa object type trên server.

## 7. Object type và input type là hai khái niệm khác nhau

Object type dùng để mô tả dữ liệu server trả về. Input object dùng để mô tả dữ liệu client được phép gửi vào. Hai nhóm này có quy tắc khác nhau:

| Đặc điểm | Object type | Input object |
|---|---|---|
| SDL keyword | **type** | **input** |
| Vị trí sử dụng | Kiểu trả về của field | Argument hoặc input variable |
| Có thể chứa field object khác | Có | Không |
| Có thể chứa interface/union | Có thể là kiểu trả về | Không |
| Có thể chứa scalar và enum | Có | Có |
| Có thể chứa list/non-null | Có | Có |

Ví dụ:

~~~graphql
type Book {
  id: ID!
  title: String!
  author: Author!
}

input CreateBookInput {
  title: String!
  authorId: ID!
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
~~~

Không thể dùng **Book** làm kiểu argument chỉ vì Java có class Book. Nếu cần gửi thông tin tạo sách, hãy định nghĩa input object riêng. Điều này cho phép API kiểm soát chính xác field nào client được phép gửi và tránh để lộ các thuộc tính nội bộ.

Không nhất thiết phải tạo một input object tương ứng một-một cho mỗi object type. Input và output thường có mục đích khác nhau. Ví dụ **Book** có **id**, **createdAt**, **author** và **internalStatus**, trong khi **CreateBookInput** chỉ nhận **title** và **authorId**.

## 8. Object type không đồng nghĩa với Java class hoặc database entity

Một object type là khái niệm của GraphQL schema. Java class, record, DTO hoặc entity là kiểu dữ liệu trong ứng dụng. Database table hoặc document là cấu trúc lưu trữ. Chúng có thể được ánh xạ với nhau nhưng không nên đồng nhất.

Ví dụ schema công khai:

~~~graphql
type Book {
  id: ID!
  title: String!
  author: Author!
}
~~~

Mô hình Java nội bộ có thể chứa thêm dữ liệu:

~~~java
public class Book {
    private String id;
    private String title;
    private String authorId;
    private BigDecimal internalCost;
    private Instant createdAt;

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getAuthorId() {
        return authorId;
    }

    public BigDecimal getInternalCost() {
        return internalCost;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
~~~

Schema chỉ công khai **id**, **title** và **author**. Việc Java class có **internalCost** không khiến client tự động truy vấn được field đó. GraphQL chỉ cho phép những field đã được khai báo trong schema.

Tách object type khỏi entity giúp:

- Không công khai nhầm dữ liệu nội bộ hoặc field nhạy cảm.
- Có thể đổi database hoặc mô hình persistence mà không phá hợp đồng API.
- Thiết kế field phù hợp nhu cầu client thay vì phụ thuộc hoàn toàn vào cấu trúc bảng.
- Tổng hợp dữ liệu từ nhiều service hoặc nguồn khác nhau.
- Tạo nhiều kiểu view công khai cho cùng một domain object khi có lý do nghiệp vụ.

Tuy nhiên, không cần tạo DTO mới cho mọi field nếu property data fetcher mặc định đã đáp ứng tốt và không có ranh giới bảo mật hay chuyển đổi đặc biệt. Hãy chọn mô hình vừa đủ rõ ràng cho schema và logic nghiệp vụ.

## 9. Field được resolve như thế nào

Khi GraphQL thực thi operation, mỗi field được giải quyết thành một giá trị. Thành phần cung cấp giá trị đó được gọi là **DataFetcher** trong GraphQL Java; trong ứng dụng Spring, method controller thường đóng vai trò resolver được ánh xạ thành data fetcher.

Đối với field con, resolver thường nhận source object, tức object kết quả từ field cha. Ví dụ:

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

Khi client truy vấn **book.author.name**, quá trình khái quát là:

1. Resolver của **Query.book** trả về một Book.
2. GraphQL dùng Book đó làm source object cho field **Book.author**.
3. Data fetcher của **Book.author** trả về Author.
4. GraphQL dùng Author làm source object cho field **Author.name**.
5. Kết quả cuối cùng được ghép theo selection set.

~~~mermaid
flowchart TD
    Q[Query.book] --> B[Book source object]
    B --> A[Book.author resolver]
    A --> AU[Author source object]
    AU --> N[Author.name resolver]
    N --> R[GraphQL response]
~~~

### Property data fetcher mặc định

Không phải field nào cũng cần viết một method resolver riêng. GraphQL Java cung cấp property data fetcher mặc định có thể lấy giá trị từ source object theo tên field. Tùy loại source object, nó có thể đọc:

- Key trong **Map** có tên tương ứng với field.
- Getter theo quy ước JavaBean như **getTitle()**.
- Boolean getter như **isPublished()**.
- Property accessor phù hợp của kiểu dữ liệu mà GraphQL Java hỗ trợ.

Ví dụ, nếu resolver trả về một Java object có **getId()** và **getTitle()**, GraphQL có thể dùng các property đó cho field **id** và **title** mà không cần viết hai resolver riêng.

Property data fetcher không tự gọi repository hoặc dịch vụ bên ngoài để tìm quan hệ. Nếu field **author** không phải property có sẵn trên source object hoặc cần truy vấn dữ liệu, hãy triển khai resolver rõ ràng.

### Resolver tường minh

Viết resolver riêng khi field cần:

- Gọi service hoặc repository.
- Kết hợp dữ liệu từ nhiều nguồn.
- Chuyển đổi định dạng hoặc áp dụng quy tắc nghiệp vụ.
- Kiểm tra quyền truy cập.
- Nhận argument để lọc, sắp xếp hoặc phân trang.
- Tối ưu tải dữ liệu bằng batch loading.

## 10. Ánh xạ object type bằng Spring for GraphQL

Spring for GraphQL cung cấp annotation để ánh xạ method Java với field trong schema. Ví dụ:

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

Controller:

~~~java
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
        return authorService.findById(book.getAuthorId());
    }
}
~~~

Trong ví dụ:

- **@QueryMapping** ánh xạ method **book** vào field **Query.book**.
- **@Argument** lấy giá trị argument **id** từ operation.
- **@SchemaMapping** ánh xạ method **author** vào field **Book.author**.
- Tham số **Book book** là source object của field **author**.

Nếu tên method trùng tên field và tên kiểu nguồn có thể được suy ra từ tham số source, có thể dùng dạng rút gọn:

~~~java
@SchemaMapping
public Author author(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

Khi tên Java method hoặc source class không phản ánh tên trong SDL, dùng **typeName** và **field** để ánh xạ tường minh. Cách này hữu ích khi Java class có tên khác với object type công khai.

Một object type không bắt buộc phải có một controller riêng. Các resolver có thể được tổ chức theo nhóm nghiệp vụ, miễn là mỗi mapping xác định đúng GraphQL type và field mà nó phục vụ.

## 11. Tải quan hệ object và vấn đề N+1

Một schema lồng nhau rất thuận tiện cho client, nhưng có thể tạo nhiều lần gọi dữ liệu nếu resolver của field con thực hiện truy vấn riêng cho từng source object.

Ví dụ query:

~~~graphql
query {
  books {
    id
    title
    author {
      name
    }
  }
}
~~~

Nếu resolver **Book.author** gọi database một lần cho mỗi sách, với 100 sách server có thể thực hiện 1 truy vấn lấy danh sách và thêm 100 truy vấn lấy tác giả. Đây là vấn đề N+1.

Có thể dùng **@BatchMapping** để gom các source object vào một lần tải:

~~~java
@Controller
public class BookRelationController {

    private final AuthorService authorService;

    public BookRelationController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(List<Book> books) {
        List<String> authorIds = books.stream()
                .map(Book::getAuthorId)
                .distinct()
                .toList();

        Map<String, Author> authors =
                authorService.findAllByIds(authorIds);

        Map<Book, Author> result = new HashMap<>();
        for (Book book : books) {
            Author author = authors.get(book.getAuthorId());
            if (author != null) {
                result.put(book, author);
            }
        }
        return result;
    }
}
~~~

Đây là ví dụ minh họa cho batch resolver; service cần trả về map được đánh chỉ mục theo author ID. Khi triển khai thực tế, cần xử lý sách không có tác giả, ID trùng, thứ tự kết quả và giá trị không tìm thấy theo nullability của schema.

DataLoader là một cơ chế khác để gom và cache các lần tải dữ liệu trong phạm vi một GraphQL execution. Nó phù hợp khi nhiều nhánh của selection set cần cùng một loại dữ liệu. Việc chọn **@BatchMapping** hay DataLoader phụ thuộc cách tổ chức resolver, yêu cầu cache và khả năng tái sử dụng batch loader.

Batch loading thay đổi cách lấy dữ liệu ở runtime, không thay đổi object type công khai. Client vẫn truy vấn **Book.author** theo cùng schema.

## 12. Nullability của field object

Field trả về object type có thể nullable hoặc non-null. Ví dụ:

~~~graphql
type Book {
  author: Author
  publisher: Publisher!
}
~~~

**author** có thể trả về null, chẳng hạn sách chưa được gán tác giả. **publisher** phải trả về một Publisher hợp lệ; nếu resolver trả null, GraphQL tạo execution error và lan truyền null lên field cha gần nhất có thể nhận null.

Với field list object:

| Khai báo | Ý nghĩa |
|---|---|
| **[Author]** | Danh sách có thể null; phần tử có thể null |
| **[Author]!** | Danh sách không null; phần tử có thể null |
| **[Author!]** | Danh sách có thể null; phần tử không null |
| **[Author!]!** | Danh sách và mọi phần tử đều không null |

Ví dụ:

~~~graphql
type Book {
  relatedBooks: [Book!]!
}
~~~

Nếu một phần tử trong danh sách vi phạm non-null, toàn bộ danh sách sẽ bị null hóa. Do field danh sách cũng non-null, lỗi có thể tiếp tục lan lên object cha. Vì vậy, hãy chọn nullability theo khả năng bảo đảm dữ liệu thực tế.

## 13. Bảo mật ở cấp object và field

Việc khai báo một field trong schema làm cho field đó có thể được client yêu cầu. Điều này không có nghĩa mọi người dùng đều được phép xem giá trị. Quyền truy cập phải được kiểm tra ở server.

Ví dụ:

~~~graphql
type Book {
  id: ID!
  title: String!
  internalNotes: String
}
~~~

Nếu **internalNotes** chỉ dành cho biên tập viên, server cần kiểm tra quyền khi resolve field hoặc ở service layer. Không nên dựa vào giao diện frontend để ẩn field vì client có thể tự gửi operation.

Với Spring Security, có thể kết hợp method security ở service hoặc resolver. Ví dụ minh họa:

~~~java
@PreAuthorize("hasAuthority('BOOK_EDITOR')")
@SchemaMapping(typeName = "Book", field = "internalNotes")
public String internalNotes(Book book) {
    return bookService.getInternalNotes(book.getId());
}
~~~

Để annotation bảo mật có hiệu lực, ứng dụng phải bật method security và cấu hình authentication/authorization phù hợp. Kiểm tra quyền trong service layer thường hữu ích khi cùng nghiệp vụ được gọi từ GraphQL, REST hoặc các luồng nội bộ khác.

Ngoài phân quyền, cần xem xét:

- Field nhạy cảm có nên xuất hiện trong schema công khai không?
- Người dùng có được phép truy cập object theo tenant hoặc owner không?
- Resolver có thể vô tình trả về object thuộc tenant khác không?
- Batch resolver có kiểm tra quyền cho từng source object không?
- Error message có làm lộ dữ liệu nội bộ hay thông tin định danh nhạy cảm không?

## 14. Tiến hóa object type an toàn

Object type là một phần hợp đồng API. Những thay đổi sau có thể ảnh hưởng client:

| Thay đổi | Tác động có thể có |
|---|---|
| Thêm field nullable | Thường tương thích với operation cũ |
| Thêm field non-null | Mọi resolver phải bảo đảm giá trị; có thể tạo lỗi runtime |
| Xóa field | Operation đang chọn field đó sẽ không còn hợp lệ |
| Đổi tên field | Tương đương xóa field cũ và thêm field mới |
| Đổi nullable thành non-null | Thay đổi cam kết dữ liệu và có thể gây lỗi nếu nguồn trả null |
| Đổi non-null thành nullable | Client phải chấp nhận khả năng nhận null |
| Thêm argument bắt buộc | Operation cũ có thể thiếu argument và không còn hợp lệ |
| Thêm argument có default | Thường ít ảnh hưởng hơn vì client cũ có thể bỏ qua |

Ví dụ khi thay field cũ:

~~~graphql
type Book {
  id: ID!
  name: String @deprecated(reason: "Sử dụng title")
  title: String!
}
~~~

Giữ field cũ trong một khoảng thời gian giúp client chuyển dần sang **title**. Trước khi xóa field deprecated, nên kiểm tra mức sử dụng và phối hợp lịch nâng cấp client.

Không nên thêm field non-null chỉ vì dữ liệu hiện tại thường có giá trị. Hãy xem xét dữ liệu lịch sử, nguồn bên ngoài, quyền truy cập và các trường hợp lỗi trước khi đưa ra cam kết mới.

## 15. Kiểm thử object type và resolver

Kiểm thử nên xác nhận cả schema công khai lẫn cách resolver cung cấp dữ liệu. Với Spring for GraphQL, **GraphQlTester** có thể thực thi operation và kiểm tra đường dẫn trong response.

Ví dụ:

~~~java
graphQlTester.document("""
        query {
            book(id: "book-01") {
                id
                title
                author {
                    name
                }
            }
        }
        """)
    .execute()
    .path("book.title")
    .entity(String.class)
    .isEqualTo("GraphQL with Spring");
~~~

Có thể bổ sung kiểm tra field quan hệ:

~~~java
graphQlTester.document("""
        query {
            book(id: "book-01") {
                author {
                    name
                }
            }
        }
        """)
    .execute()
    .path("book.author.name")
    .entity(String.class)
    .isEqualTo("Ada Lovelace");
~~~

Các tình huống nên kiểm thử:

1. Object tồn tại và các field cơ bản trả về đúng giá trị.
2. Object không tồn tại và root field trả về null theo schema.
3. Field quan hệ không có dữ liệu và xử lý đúng nullability.
4. Argument được truyền, bỏ qua hoặc nhận giá trị mặc định đúng cách.
5. User không đủ quyền không thể đọc field được bảo vệ.
6. Batch resolver xử lý danh sách rỗng, ID trùng và phần tử không tìm thấy.
7. Resolver lỗi tạo GraphQL error và null propagation đúng như hợp đồng.
8. Operation có selection set sai bị từ chối trong validation.

Unit test cho service vẫn quan trọng vì GraphQL tester không thay thế việc kiểm thử logic nghiệp vụ. Nên giữ test tập trung vào hành vi mà người dùng API quan sát được.

## 16. Những lỗi thiết kế object type thường gặp

| Lỗi | Vì sao có vấn đề | Hướng xử lý |
|---|---|---|
| Dùng object type làm argument | Object type là output type | Tạo input object |
| Đưa mọi field của entity vào schema | Có thể làm lộ dữ liệu nội bộ | Thiết kế object type theo hợp đồng công khai |
| Đánh dấu mọi field là non-null | Không phản ánh các trường hợp dữ liệu thiếu | Chọn nullability theo khả năng bảo đảm |
| Viết resolver cho mọi property đơn giản | Tăng code và độ phức tạp không cần thiết | Dùng property data fetcher khi phù hợp |
| Resolver field quan hệ truy vấn riêng cho từng source | Dễ phát sinh N+1 | Dùng batch loading hoặc DataLoader |
| Không giới hạn argument phân trang | Client có thể yêu cầu tập dữ liệu quá lớn | Validation và giới hạn kích thước |
| Field đệ quy không có giới hạn query | Query sâu có thể tiêu tốn nhiều tài nguyên | Giới hạn depth/complexity |
| Chỉ kiểm tra quyền ở frontend | Client có thể gọi field trực tiếp | Kiểm tra authorization ở server |
| Đổi tên field ngay lập tức | Operation client cũ không còn hợp lệ | Thêm field mới, deprecate field cũ, rồi loại bỏ có kế hoạch |

## 17. Quy trình thiết kế object type

Khi thiết kế object type mới cho Spring for GraphQL, có thể thực hiện theo trình tự:

1. Xác định object này đại diện cho khái niệm nghiệp vụ nào và client nào cần đọc nó.
2. Chọn các field công khai, tên field và kiểu output tương ứng.
3. Xác định field scalar, enum, object relation, interface/union và list.
4. Chọn nullability theo dữ liệu thực tế và khả năng bảo đảm của resolver.
5. Thiết kế argument và input object riêng nếu field cần tham số.
6. Xác định field nào dùng property data fetcher mặc định và field nào cần resolver tường minh.
7. Kiểm tra quan hệ lồng nhau có tạo nguy cơ N+1 hoặc query quá sâu không.
8. Đặt authorization ở server cho object và field nhạy cảm.
9. Viết operation mẫu và kiểm thử bằng GraphQlTester.
10. Đánh giá khả năng tương thích trước khi đổi field hoặc nullability đã công khai.

Object type là cấu trúc mà client nhìn thấy khi đọc dữ liệu từ GraphQL API. Thiết kế tốt giúp client truy vấn đúng phần dữ liệu cần thiết, đồng thời giữ server tự do tổ chức Java model, persistence và cách tải dữ liệu. Trong Spring for GraphQL, SDL xác định hợp đồng; property data fetcher và các resolver như **@SchemaMapping** cung cấp giá trị; còn batch loading, bảo mật và kiểm thử bảo đảm object được trả về đúng, an toàn và hiệu quả.
