# Nested field selection

GraphQL cho phép client chọn field lồng nhau để nhận dữ liệu theo cấu trúc object mà API công bố. Thay vì gọi nhiều endpoint để lấy một quyển sách, tác giả và danh sách đánh giá, client có thể mô tả toàn bộ dữ liệu cần thiết trong một operation. Phần mô tả field bên trong field được gọi là **nested field selection**.

Trong Spring for GraphQL, GraphQL engine đọc selection set và phân giải từng field theo schema. Spring kết nối các field đó với dữ liệu trả về từ object hoặc các method resolver như `@SchemaMapping`. Hiểu cách selection set hoạt động giúp thiết kế response rõ ràng, triển khai resolver đúng chỗ và kiểm soát truy vấn lồng nhau có thể gây N+1.

## 1. Selection set là gì?

Selection set là nhóm field nằm trong cặp dấu ngoặc nhọn của một operation hoặc của một field trả về object.

Ví dụ schema:

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

Client có thể chọn sách và tác giả trong cùng một request:

~~~graphql
query BookDetail {
    book(id: "book-42") {
        id
        title
        author {
            id
            name
        }
    }
}
~~~

Cấu trúc này có ba cấp:

1. Root field `book` thuộc type `Query`.
2. Các field `id`, `title`, `author` thuộc type `Book`.
3. Các field `id`, `name` thuộc type `Author`.

Selection set của `book` nằm bên trong field `book`; selection set của `author` nằm bên trong field `author`. Mỗi cấp phải tuân theo type của field cha.

Response có cấu trúc tương ứng:

~~~json
{
    "data": {
        "book": {
            "id": "book-42",
            "title": "Spring in Action",
            "author": {
                "id": "author-7",
                "name": "Lan"
            }
        }
    }
}
~~~

Client quyết định field nào xuất hiện trong response. Nếu không chọn `author`, server không cần trả object tác giả trong kết quả operation đó.

## 2. Quy tắc chọn field theo kiểu dữ liệu

GraphQL phân biệt kiểu leaf và kiểu composite khi validate selection set.

| Kiểu trả về | Cách chọn |
| --- | --- |
| Scalar như `String`, `Int`, `Boolean`, `ID` | Chọn trực tiếp, không có selection set con. |
| Enum | Chọn trực tiếp, không có selection set con. |
| Object | Phải có selection set để chỉ rõ field con. |
| Interface | Phải có selection set; có thể dùng inline fragment để chọn field riêng của implementation. |
| Union | Phải có selection set; thường dùng inline fragment để lấy field theo concrete type. |
| List | Cách chọn phụ thuộc kiểu phần tử; list object cần selection set cho từng object. |

Ví dụ hợp lệ:

~~~graphql
query {
    book(id: "book-42") {
        title
        author {
            name
        }
    }
}
~~~

Ví dụ sai vì field `author` trả về object nhưng không có selection set:

~~~graphql
query {
    book(id: "book-42") {
        title
        author
    }
}
~~~

Ví dụ sai vì `title` là scalar:

~~~graphql
query {
    book(id: "book-42") {
        title {
            length
        }
    }
}
~~~

Quy tắc này được kiểm tra trước khi resolver chạy. Nếu selection set không phù hợp với kiểu trong schema, GraphQL trả lỗi validation và không thực thi operation.

### List object cũng là nested selection

Một field trả về list object cần selection set giống một field trả về một object đơn:

~~~graphql
type Book {
    id: ID!
    title: String!
    reviews: [Review!]!
}

type Review {
    id: ID!
    rating: Int!
    comment: String
}
~~~

Client chọn các field trên mỗi phần tử:

~~~graphql
query BookReviews {
    book(id: "book-42") {
        title
        reviews {
            id
            rating
            comment
        }
    }
}
~~~

Response:

~~~json
{
    "data": {
        "book": {
            "title": "Spring in Action",
            "reviews": [
                {
                    "id": "review-1",
                    "rating": 5,
                    "comment": "Rất hữu ích"
                },
                {
                    "id": "review-2",
                    "rating": 4,
                    "comment": null
                }
            ]
        }
    }
}
~~~

Selection set mô tả cấu trúc của từng phần tử trong list. Nếu list rỗng, response chứa mảng rỗng; nếu field cho phép null, kết quả cũng có thể là null theo hợp đồng schema.

## 3. Selection set có thể lồng nhiều cấp

Một operation có thể đi qua nhiều quan hệ object. Ví dụ hệ thống thư viện có Book, Author, Publisher và Address:

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
    publisher: Publisher
}

type Publisher {
    name: String!
    address: Address
}

type Address {
    city: String!
    country: String!
}
~~~

Client có thể chọn nhiều cấp:

~~~graphql
query BookPublisher {
    book(id: "book-42") {
        title
        author {
            name
            publisher {
                name
                address {
                    city
                    country
                }
            }
        }
    }
}
~~~

Response phản ánh đúng quan hệ lồng nhau:

~~~json
{
    "data": {
        "book": {
            "title": "Spring in Action",
            "author": {
                "name": "Lan",
                "publisher": {
                    "name": "Tech Books",
                    "address": {
                        "city": "Ho Chi Minh City",
                        "country": "Vietnam"
                    }
                }
            }
        }
    }
}
~~~

Việc có thể chọn sâu không có nghĩa client nên truy vấn sâu tùy ý. Một field con có thể kích hoạt truy vấn database, gọi dịch vụ từ xa hoặc thực hiện tính toán tốn kém. Khi schema có quan hệ lồng nhau nhiều cấp, server cần kiểm soát độ sâu và chi phí operation.

## 4. Argument trên nested field

Argument không chỉ xuất hiện ở root field. Bất kỳ field nào trong schema cũng có thể khai báo argument nếu nghiệp vụ cần tham số riêng.

Ví dụ:

~~~graphql
type Book {
    id: ID!
    title: String!
    reviews(first: Int = 10, minRating: Int): [Review!]!
}

type Review {
    id: ID!
    rating: Int!
    comment: String
}
~~~

Client có thể truyền argument trực tiếp vào field lồng nhau:

~~~graphql
query BookReviewPreview {
    book(id: "book-42") {
        title
        reviews(first: 3, minRating: 4) {
            rating
            comment
        }
    }
}
~~~

Ở đây `first` và `minRating` thuộc field `Book.reviews`, không thuộc `Query.book`. Điều này giúp mỗi quan hệ có thể định nghĩa cách lọc hoặc giới hạn riêng.

Trong Spring for GraphQL, resolver của field lồng nhau nhận source object và argument:

~~~java
@Controller
public class BookReviewController {

    private final ReviewService reviewService;

    public BookReviewController(ReviewService reviewService) {
        this.reviewService = reviewService;
    }

    @SchemaMapping(typeName = "Book", field = "reviews")
    public List<Review> reviews(
            Book book,
            @Argument("first") Integer first,
            @Argument("minRating") Integer minRating) {
        return reviewService.findReviews(book.id(), first, minRating);
    }
}
~~~

Tham số `Book book` là object nguồn mà field `reviews` đang được phân giải. `@Argument` lấy các giá trị được client truyền trên chính field này.

Cần xác định rõ giá trị mặc định và giới hạn ở lớp nghiệp vụ. Ví dụ `first` có default trong SDL nhưng client vẫn có thể truyền số âm hoặc một con số quá lớn nếu schema chỉ khai báo kiểu `Int`. Resolver nên kiểm tra và áp dụng giới hạn tối đa.

## 5. Spring for GraphQL phân giải nested field như thế nào?

GraphQL Java thực thi operation theo schema. Khi một field trả về object, engine tiếp tục phân giải những field mà client đã chọn trên object đó. Spring for GraphQL cung cấp các method mapping để ứng dụng xử lý những field cần logic riêng.

Luồng tổng quát:

~~~mermaid
flowchart TD
    A["Client gửi selection set"] --> B["GraphQL validate theo schema"]
    B --> C["Resolver root: Query.book"]
    C --> D["Trả về Book"]
    D --> E["Đọc các field được chọn trên Book"]
    E --> F["Property access hoặc @SchemaMapping"]
    F --> G["Trả về Author / Review"]
    G --> H["Tiếp tục phân giải field con"]
    H --> I["Tạo response theo selection set"]
~~~

Ví dụ schema:

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

Resolver root:

~~~java
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

Nếu object `Book` đã cung cấp thuộc tính `id` và `title` qua getter hoặc accessor, GraphQL có thể lấy các giá trị đó bằng property data fetcher mặc định. Không phải mọi field đều cần viết một method resolver riêng.

Khi field cần truy vấn thêm dữ liệu hoặc thực thi logic, dùng `@SchemaMapping`:

~~~java
@Controller
public class BookAuthorController {

    private final AuthorService authorService;

    public BookAuthorController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }
}
~~~

Method này ánh xạ field `author` của type `Book`. Spring truyền source object `Book` vào tham số đầu tiên, sau đó method dùng dữ liệu trong Book để tìm Author.

Có thể bỏ `typeName` hoặc `field` trong một số trường hợp vì Spring có thể suy ra từ tên method và kiểu tham số source. Tuy nhiên, ghi rõ tên giúp mapping dễ đọc, đặc biệt khi schema có nhiều type hoặc method Java có tên khác field.

### Khi nào cần @SchemaMapping?

Dùng property access khi giá trị đã có sẵn trên object nguồn và không cần logic bổ sung. Dùng `@SchemaMapping` khi cần:

- Đọc quan hệ từ repository hoặc service.
- Chuyển đổi hoặc tính toán giá trị field.
- Truyền argument của nested field xuống service.
- Áp dụng quy tắc nghiệp vụ hoặc xử lý lỗi riêng cho field.
- Kết hợp với DataLoader để tải dữ liệu theo batch.

Không nên tạo resolver chỉ để đọc lại một thuộc tính đơn giản nếu property access đã đáp ứng đúng hợp đồng schema. Số resolver và độ phức tạp của chúng nên phản ánh logic thực sự cần thiết.

## 6. Fragments trong nested selection

Khi nhiều operation hoặc nhiều nhánh cần chọn cùng một nhóm field, có thể dùng fragment để tái sử dụng selection set.

~~~graphql
fragment AuthorSummary on Author {
    id
    name
}

query BookAndAuthor {
    book(id: "book-42") {
        id
        title
        author {
            ...AuthorSummary
        }
    }
}
~~~

Fragment `AuthorSummary` được định nghĩa trên type `Author`. Khi sử dụng bên trong `author`, GraphQL kiểm tra fragment phù hợp với kiểu của field đó.

Fragment có thể được dùng lồng nhau:

~~~graphql
fragment PublisherDetails on Publisher {
    name
    address {
        city
        country
    }
}

fragment AuthorDetails on Author {
    id
    name
    publisher {
        ...PublisherDetails
    }
}

query BookDetails {
    book(id: "book-42") {
        title
        author {
            ...AuthorDetails
        }
    }
}
~~~

Fragments chỉ tái sử dụng cấu trúc selection set. Chúng không tạo thêm endpoint hay resolver riêng; các field vẫn được thực thi theo schema và mapping hiện có.

### Inline fragments với interface và union

Nếu field trả về interface hoặc union, client có thể dùng inline fragment để chọn field cụ thể theo type thực tế.

~~~graphql
interface SearchResult {
    id: ID!
}

type Book implements SearchResult {
    id: ID!
    title: String!
}

type Author implements SearchResult {
    id: ID!
    name: String!
}

type Query {
    search(keyword: String!): [SearchResult!]!
}
~~~

Operation:

~~~graphql
query Search($keyword: String!) {
    search(keyword: $keyword) {
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

`__typename` là meta field cho biết concrete type của object. Inline fragment `... on Book` chỉ chọn field `title` khi kết quả là Book; fragment `... on Author` chọn `name` khi kết quả là Author.

Cách này hữu ích khi một danh sách kết quả chứa nhiều loại object khác nhau. Client vẫn nhận được response thống nhất nhưng có thể xử lý riêng theo type.

## 7. Nhiều field lồng nhau và vấn đề N+1

Nested selection giúp client lấy dữ liệu liên quan trong một operation. Tuy nhiên, một request HTTP duy nhất không đồng nghĩa server chỉ thực hiện một truy vấn database.

Giả sử client lấy 50 sách và chọn tác giả:

~~~graphql
query BooksWithAuthors {
    books {
        id
        title
        author {
            id
            name
        }
    }
}
~~~

Nếu resolver `Book.author` gọi repository một lần cho từng quyển sách, server có thể thực hiện:

- Một truy vấn lấy danh sách 50 sách.
- 50 truy vấn riêng để lấy 50 tác giả.

Đây là vấn đề N+1. Số lần truy cập dữ liệu tăng theo số phần tử cha, làm request chậm khi danh sách lớn.

Có thể giải quyết bằng DataLoader hoặc `@BatchMapping`. Ví dụ:

~~~java
@Controller
public class BookAuthorController {

    private final AuthorService authorService;

    public BookAuthorController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(List<Book> books) {
        List<String> authorIds = books.stream()
                .map(Book::authorId)
                .distinct()
                .toList();

        Map<String, Author> authorsById =
                authorService.findAllByIds(authorIds);

        return books.stream()
                .filter(book -> authorsById.containsKey(book.authorId()))
                .collect(Collectors.toMap(
                        book -> book,
                        book -> authorsById.get(book.authorId())
                ));
    }
}
~~~

`@BatchMapping` gom các source object Book cần phân giải field author vào một lần gọi method batch. Ví dụ trên lấy các author ID duy nhất, tải tác giả theo lô và trả map liên kết từng Book với Author tương ứng.

Cần bảo đảm implementation batch xử lý đúng các trường hợp:

- Nhiều Book tham chiếu cùng một Author.
- Không tìm thấy Author tương ứng.
- Kết quả truy vấn theo lô không trả về đúng thứ tự đầu vào.
- Một số source object có quan hệ null hoặc thiếu khóa liên kết.

Nếu dùng DataLoader trực tiếp, batch loader phải trả kết quả theo đúng quy tắc mapping mà DataLoader yêu cầu. Không được giả định thứ tự kết quả từ database luôn trùng thứ tự danh sách key đã gửi.

### Đo hiệu quả batching

Nên kiểm tra số lần gọi repository hoặc database trước và sau khi batch:

| Tình huống | Resolver riêng từng Book | Batch resolver |
| --- | --- | --- |
| Lấy 1 Book | Một lần tải Author | Một batch tải Author |
| Lấy 20 Book | Có thể 20 lần tải Author | Một batch cho nhóm Book |
| Nhiều Book cùng Author | Có thể tải lặp cùng Author | Có thể loại ID trùng trước khi tải |

Số lần gọi cụ thể còn phụ thuộc cách phân trang, phạm vi dispatch của DataLoader và cách triển khai service. Hãy đo bằng log, metrics hoặc test spy thay vì dựa vào giả định.

## 8. Nested selection không đồng nghĩa với việc luôn tải mọi quan hệ

Client chỉ chọn field cần dùng. Resolver cũng nên thực hiện công việc tương ứng với field được yêu cầu. Nếu operation chỉ chọn:

~~~graphql
query BookTitles {
    books {
        id
        title
    }
}
~~~

thì GraphQL không cần phân giải `Book.author` hoặc `Book.reviews`. Resolver của các field đó không được gọi chỉ vì chúng tồn tại trong schema.

Đây là lợi ích của GraphQL: client mô tả chính xác shape dữ liệu muốn nhận. Tuy nhiên, nếu resolver root luôn join và tải mọi quan hệ trước khi GraphQL biết selection set, ứng dụng có thể vẫn đọc dư dữ liệu. Thiết kế repository và query database nên cân nhắc nhu cầu thực tế của operation.

Trong các trường hợp tối ưu nâng cao, GraphQL Java cung cấp thông tin selection set qua `DataFetchingFieldSelectionSet`. Resolver hoặc service có thể dùng thông tin đó để chọn chiến lược truy vấn phù hợp, nhưng cần cẩn trọng với alias, fragment và field lồng nhau. Không nên biến selection set thành cơ chế phân quyền; authorization phải được kiểm tra độc lập ở server.

## 9. Bảo mật và giới hạn nested selection

Một client có thể yêu cầu nhiều cấp object, gọi nhiều field lồng nhau hoặc lặp lại một field với argument khác nhau. Vì vậy, API production cần đặt giới hạn hợp lý.

**Kiểm tra quyền trên từng field.** Người dùng được phép đọc Book không đồng nghĩa được phép đọc mọi dữ liệu lồng nhau như thông tin riêng tư của Author hoặc dữ liệu nội bộ của Publisher.

**Giới hạn độ sâu.** Tránh operation có thể đi qua quan hệ lồng nhau quá sâu hoặc chu kỳ quan hệ gây chi phí lớn.

**Giới hạn độ phức tạp.** Một field list có thể trả về nhiều phần tử; kết hợp với nested list sẽ làm số object tăng rất nhanh. Cần giới hạn page size, query complexity hoặc chi phí theo field.

**Kiểm tra argument tại nested field.** Các tham số như `first`, `limit`, `offset` phải được validate và giới hạn ở server.

**Không để resolver lộ dữ liệu nhạy cảm.** Selection set là yêu cầu của client, không phải quyền truy cập. Server phải quyết định field nào người dùng hiện tại được phép xem.

Ví dụ một Book có field `internalNotes` không nên được trả về chỉ vì client thêm tên field đó vào operation. Quyền truy cập cần được bảo vệ tại resolver hoặc lớp bảo mật tương ứng.

## 10. Các lỗi thường gặp khi chọn nested field

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Object field báo thiếu selection set | Client chọn field object mà không chọn field con. | Bổ sung selection set phù hợp với object type. |
| Scalar hoặc enum báo lỗi selection set | Client đặt ngoặc nhọn sau leaf field. | Chọn trực tiếp scalar hoặc enum. |
| Nested field trả null | Source object thiếu dữ liệu hoặc resolver trả null. | Kiểm tra source, property accessor và mapping. |
| Resolver nested không được gọi | Field không nằm trong selection set hoặc mapping không khớp type/field. | Kiểm tra operation và annotation @SchemaMapping. |
| Nested argument nhận null | Argument đặt sai field hoặc tên @Argument không khớp schema. | Đặt argument trên đúng field và kiểm tra tên. |
| Response có shape khác dự kiến | Alias, fragment hoặc selection set tạo key/nhánh khác. | Đối chiếu operation và response theo từng cấp. |
| Query nhiều object bị chậm | Resolver con truy cập dữ liệu riêng cho từng object. | Đo số truy vấn và áp dụng DataLoader hoặc @BatchMapping. |
| Field lồng nhau bị từ chối | Quyền truy cập hoặc giới hạn độ sâu/chi phí chặn operation. | Kiểm tra security policy và giới hạn truy vấn. |

Khi debug, hãy bắt đầu từ schema và operation document. Xác nhận từng field có đúng type và selection set chưa, sau đó kiểm tra root resolver, source object và nested resolver. Nếu dữ liệu đúng nhưng thời gian phản hồi tăng theo số object, đo số lần gọi service/repository để xác định N+1.

## 11. Kiểm thử nested field selection

Dùng `GraphQlTester` để kiểm tra một operation có nested selection:

~~~java
@Test
void returnsBookWithAuthor() {
    graphQlTester.document("""
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
            """)
        .variable("id", "book-42")
        .execute()
        .path("book.author.name")
        .entity(String.class)
        .isEqualTo("Lan");
}
~~~

Ngoài kiểm tra giá trị trả về, nên kiểm tra:

- Field con nullable trả null đúng khi quan hệ không tồn tại.
- Field non-null xử lý lỗi theo quy tắc null propagation.
- Nested field nhận đúng argument và áp dụng filter/pagination.
- Fragment và alias tạo response key đúng.
- Resolver không được gọi khi field không nằm trong selection set.
- Batch resolver giảm số lần gọi repository khi xử lý nhiều parent object.
- Người dùng không đủ quyền không thể đọc field nhạy cảm.

Để kiểm tra N+1, có thể dùng mock hoặc spy trên repository và xác minh số lần gọi. Với kiểm thử tích hợp, dùng dữ liệu có nhiều parent object và nhiều object con để đo số truy vấn thực tế.

## 12. Những điểm cần ghi nhớ

- Nested field selection là cách client mô tả dữ liệu object lồng nhau trong một operation.
- Object, interface, union và list object cần selection set phù hợp; scalar và enum là leaf field.
- Argument có thể được khai báo ở nested field, không chỉ ở root Query.
- Spring for GraphQL dùng property access cho thuộc tính có sẵn và `@SchemaMapping` cho logic phân giải field riêng.
- Fragments giúp tái sử dụng selection set; inline fragments xử lý field theo concrete type của interface hoặc union.
- Một request GraphQL có thể tạo nhiều lần truy cập dữ liệu phía server; DataLoader và `@BatchMapping` giúp xử lý N+1.
- Selection set không thay thế authorization; server vẫn phải kiểm tra quyền và giới hạn chi phí operation.

Nested field selection giúp client nhận đúng cấu trúc dữ liệu cần dùng qua một GraphQL operation. Khi kết hợp schema rõ ràng, resolver có trách nhiệm và batching phù hợp, ứng dụng Spring for GraphQL có thể phục vụ các quan hệ dữ liệu phức tạp mà vẫn giữ được hiệu năng và khả năng kiểm soát.

