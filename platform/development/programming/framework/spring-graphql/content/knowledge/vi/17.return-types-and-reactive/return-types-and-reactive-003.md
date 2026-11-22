# Collection return type

Trong GraphQL, một field có thể trả về một danh sách giá trị. Ví dụ, field books trả về nhiều quyển sách, authors trả về danh sách tác giả hoặc tags trả về danh sách chuỗi. Trong schema, danh sách được biểu diễn bằng cặp ngoặc vuông; trong Java, resolver thường trả về List<T> hoặc một kiểu collection phù hợp. **Collection return type** là cách đưa một tập hợp kết quả từ Java vào field có kiểu list trong GraphQL.

Với Spring for GraphQL, controller method có thể trả về List, Collection hoặc kiểu kết quả phù hợp mà GraphQL Java có thể xử lý như danh sách. Spring đăng ký phương thức làm data fetcher; GraphQL runtime dùng kiểu field trong SDL để kiểm tra, phân giải từng phần tử và tạo response. Vì vậy, cần thiết kế đồng thời kiểu list trong SDL, kiểu collection Java, quy tắc nullability và thứ tự kết quả.

## Khai báo list trong GraphQL SDL

GraphQL dùng dấu ngoặc vuông để khai báo một list type:

~~~graphql
type Query {
  books: [Book]
  titles: [String]
  ratings: [Int]
}

type Book {
  id: ID!
  title: String!
}
~~~

[Book] nghĩa là field books trả về một danh sách Book. Mỗi phần tử của danh sách có thể là null và bản thân danh sách cũng có thể là null. Tương tự, [String] là danh sách chuỗi và [Int] là danh sách số nguyên.

List có thể lồng nhau:

~~~graphql
type Query {
  matrix: [[Int]]
}
~~~

Field matrix trả về một danh sách các danh sách số nguyên. Kiểu lồng nhau có thể hữu ích cho dữ liệu dạng ma trận hoặc nhóm theo ngày, nhưng với dữ liệu nghiệp vụ, một object type có tên thường dễ hiểu và dễ mở rộng hơn một cấu trúc list lồng sâu.

## Kết hợp list với non-null

Dấu chấm than có thể áp dụng cho list hoặc cho từng phần tử. Vị trí của dấu này quyết định danh sách và phần tử có được phép null hay không:

| Kiểu SDL | Danh sách có thể null? | Phần tử có thể null? |
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

Với khai báo này, field books phải trả về một danh sách khác null và mọi phần tử trong danh sách cũng phải khác null. Danh sách rỗng [] vẫn hợp lệ vì danh sách có thể không chứa phần tử nào mà không phải là null.

Nullability là hợp đồng GraphQL, không được suy ra tự động từ kiểu Java List<Book>. Nếu SDL khai báo [Book!]!, resolver cần cung cấp một collection khác null và không chứa phần tử null. Nếu resolver trả về null hoặc có phần tử null, GraphQL tạo lỗi thực thi và áp dụng quy tắc null propagation lên field cha gần nhất có thể nhận null.

Ví dụ, nếu một phần tử null trong danh sách [Book!]!, toàn bộ field books trở thành null do phần tử bị khai báo non-null; vì chính field books cũng non-null, null tiếp tục lan lên parent. Nếu field này nằm trực tiếp trên Query root, response có thể có data: null. Vì vậy, chỉ dùng non-null khi ứng dụng thực sự bảo đảm được điều kiện đó.

## List rỗng và null khác nhau

Hai kết quả sau có ý nghĩa khác nhau:

~~~json
{
  "data": {
    "books": []
  }
}
~~~

Danh sách rỗng nghĩa là truy vấn thành công nhưng không có quyển sách nào phù hợp.

~~~json
{
  "data": {
    "books": null
  }
}
~~~

Giá trị null có thể biểu thị field không có giá trị, không thể phân giải hoặc lỗi đã xảy ra nếu schema cho phép null tại vị trí đó. Với field danh sách mà không tìm thấy bản ghi, thông thường nên trả collection rỗng thay vì null.

Trong Java:

~~~java
return List.of();
~~~

trả về danh sách rỗng. Còn:

~~~java
return null;
~~~

trả về null và có thể gây lỗi nếu SDL khai báo field là non-null. Hãy thống nhất quy ước ở service để controller không phải đoán ý nghĩa của null.

## Dùng List trong annotated controller

Ví dụ schema:

~~~graphql
type Query {
  books: [Book!]!
}

type Book {
  id: ID!
  title: String!
  publishedYear: Int
}
~~~

Controller trả về List<Book>:

~~~java
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
~~~

Service có thể trả về collection từ repository:

~~~java
public interface BookRepository extends JpaRepository<Book, String> {
}

@Service
public class BookService {

    private final BookRepository bookRepository;

    public BookService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    public List<Book> findAll() {
        return bookRepository.findAll();
    }
}
~~~

GraphQL runtime nhận danh sách và phân giải từng phần tử theo kiểu Book. Nếu client chỉ chọn id và title, runtime chỉ cần thực thi các field đó trong selection set:

~~~graphql
query {
  books {
    id
    title
  }
}
~~~

Response có cấu trúc danh sách object:

~~~json
{
  "data": {
    "books": [
      {
        "id": "book-101",
        "title": "Spring in Action"
      },
      {
        "id": "book-102",
        "title": "GraphQL in Action"
      }
    ]
  }
}
~~~

Kiểu trả về Java không quyết định client được chọn field nào. SDL và selection set quyết định hình dạng response; collection chỉ cung cấp các object nguồn để GraphQL tiếp tục phân giải.

## Collection, Iterable và array

Java có nhiều kiểu biểu diễn một tập hợp:

| Kiểu Java | Đặc điểm | Khi dùng làm kết quả GraphQL |
| --- | --- | --- |
| List<T> | Có thứ tự, cho phép phần tử trùng lặp | Lựa chọn phổ biến cho field list |
| Collection<T> | Giao diện chung của nhiều collection | Phù hợp khi service không cần cam kết kiểu list cụ thể |
| Set<T> | Không cho phần tử trùng theo equals/hashCode | Chỉ dùng khi không cần thứ tự hoặc có quy tắc thứ tự rõ |
| Iterable<T> | Cho phép duyệt các phần tử | Có thể dùng khi nguồn dữ liệu chỉ cung cấp khả năng lặp |
| T[] | Mảng có kích thước cố định sau khi tạo | Có thể dùng nhưng thường kém linh hoạt hơn List |

GraphQL Java xử lý list value từ các cấu trúc có thể duyệt như Iterable và mảng. Trong ứng dụng Spring for GraphQL, List<T> thường là lựa chọn dễ đọc và dự đoán nhất vì thể hiện rõ một danh sách có thứ tự.

Không nên trả Set<T> chỉ vì repository hiện tại dùng Set. Set không bảo đảm thứ tự theo hợp đồng chung; một query có thể trả phần tử theo thứ tự khác nhau giữa các lần chạy hoặc giữa các implementation. Nếu API cần thứ tự ổn định, hãy sắp xếp rõ ràng rồi trả List<T>.

Ví dụ chuyển Set sang List có thứ tự:

~~~java
public List<Book> findAllSorted() {
    return bookRepository.findAll().stream()
            .sorted(Comparator.comparing(Book::title))
            .toList();
}
~~~

Với Java version chưa hỗ trợ Stream.toList(), có thể dùng collect(Collectors.toList()). Thứ tự nên được quy định ở repository hoặc service để mọi client nhận cùng một hợp đồng.

## Thứ tự phần tử trong response

GraphQL giữ thứ tự phần tử mà data fetcher trả về. Nếu resolver trả về List có thứ tự, response giữ thứ tự đó. Tuy nhiên, database không bảo đảm thứ tự nếu câu query không có ORDER BY.

Ví dụ:

~~~java
public List<Book> findByPublishedYear() {
    return bookRepository.findAllByOrderByPublishedYearDesc();
}
~~~

Nếu thứ tự là một phần của API, hãy mô tả rõ sort mặc định hoặc nhận argument sort từ client. Không nên phụ thuộc vào thứ tự tình cờ của database hay HashSet.

Khi client cần chọn thứ tự:

~~~graphql
enum BookSort {
  TITLE_ASC
  TITLE_DESC
  PUBLISHED_YEAR_DESC
}

type Query {
  books(sort: BookSort = TITLE_ASC): [Book!]!
}
~~~

Resolver có thể chuyển enum sang tiêu chí sắp xếp được cho phép:

~~~java
@QueryMapping
public List<Book> books(@Argument BookSort sort) {
    return bookService.findAll(sort);
}
~~~

Chỉ ánh xạ enum sang các thuộc tính sort đã được ứng dụng hỗ trợ. Không nối trực tiếp tên field tùy ý từ client vào câu SQL.

## Collection lồng trong object type

List không chỉ xuất hiện ở Query root. Một object type có thể chứa field trả về collection:

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

Nếu thuộc tính reviews đã có sẵn trên Java object và có thể đọc trực tiếp, GraphQL có thể sử dụng property access mặc định. Nếu cần truy vấn dữ liệu liên quan, viết resolver cho field:

~~~java
@Controller
public class BookFieldController {

    private final ReviewService reviewService;

    public BookFieldController(ReviewService reviewService) {
        this.reviewService = reviewService;
    }

    @SchemaMapping(typeName = "Book", field = "reviews")
    public List<Review> reviews(Book book) {
        return reviewService.findByBookId(book.id());
    }
}
~~~

Tham số Book là source object. Resolver trả về một collection Review; GraphQL tiếp tục phân giải các field của từng Review theo selection set.

List lồng nhau cũng có thể xuất hiện trong input hoặc output object. Tuy nhiên, nếu một field quan hệ có thể chứa hàng nghìn phần tử, nên thiết kế argument phân trang thay vì luôn trả toàn bộ collection.

## Trả DTO thay vì entity persistence

Repository có thể trả về entity JPA/Hibernate, nhưng không phải lúc nào cũng nên đưa entity trực tiếp ra GraphQL. Entity có thể chứa quan hệ lazy, proxy, field nội bộ hoặc dữ liệu không nên công khai. Một lựa chọn rõ ràng hơn là chuyển entity sang DTO trước khi trả về:

~~~java
public record BookSummary(
        String id,
        String title,
        Integer publishedYear) {
}
~~~

~~~java
public interface BookEntityRepository extends JpaRepository<BookEntity, String> {
}

@Service
public class BookService {

    private final BookEntityRepository repository;

    public BookService(BookEntityRepository repository) {
        this.repository = repository;
    }

    public List<BookSummary> findAll() {
        return repository.findAll().stream()
                .map(entity -> new BookSummary(
                        entity.getId(),
                        entity.getTitle(),
                        entity.getPublishedYear()))
                .toList();
    }
}
~~~

Schema tương ứng:

~~~graphql
type Query {
  books: [BookSummary!]!
}

type BookSummary {
  id: ID!
  title: String!
  publishedYear: Int
}
~~~

DTO giúp kiểm soát field công khai, tách schema khỏi persistence model và tránh để GraphQL vô tình truy cập property nội bộ. Nếu mapping cần đọc quan hệ lazy, hãy thực hiện trong transaction hoặc dùng projection/query phù hợp để dữ liệu cần thiết được tải có chủ đích.

Trong ví dụ này, repository dùng JpaRepository để findAll() trả về List<BookEntity>. Nếu repository chỉ kế thừa CrudRepository, findAll() có kiểu Iterable; khi đó hãy duyệt Iterable hoặc chuyển nó thành List trước khi gọi stream().

## Collection và vấn đề N+1

Một resolver trả về collection có thể khiến GraphQL gọi resolver con cho từng phần tử. Ví dụ Query trả về 100 Book và client chọn field author:

~~~graphql
type Book {
  id: ID!
  title: String!
  author: Author!
}
~~~

Nếu mỗi lần phân giải author đều gọi database riêng, một query có thể tạo ra một truy vấn lấy danh sách sách và 100 truy vấn lấy tác giả. Đây là vấn đề N+1.

Spring for GraphQL hỗ trợ @BatchMapping và DataLoader để gom các lần tải dữ liệu liên quan:

~~~java
@Controller
public class BookBatchController {

    private final AuthorService authorService;

    public BookBatchController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(List<Book> books) {
        return authorService.findAuthorsFor(books);
    }
}
~~~

Batch service cần tải tác giả theo nhóm ID thay vì lặp lại một query cho từng Book. Với batch mapping, cần bảo đảm kết quả được ánh xạ đúng source object; nếu dùng DataLoader trực tiếp, phải giữ đúng quan hệ giữa key và value.

Collection lớn không chỉ tốn số lần truy vấn mà còn tốn bộ nhớ và thời gian serialize. Hãy kết hợp batching với phân trang và giới hạn độ phức tạp operation.

## Phân trang thay vì trả collection không giới hạn

Một field trả toàn bộ collection phù hợp với tập dữ liệu nhỏ, nhưng không phù hợp với danh mục có thể tăng liên tục. Có thể thêm argument page và size:

~~~graphql
type Query {
  books(page: Int = 0, size: Int = 20): [Book!]!
}
~~~

~~~java
@QueryMapping
public List<BookSummary> books(
        @Argument Integer page,
        @Argument Integer size) {
    int safePage = Math.max(page == null ? 0 : page, 0);
    int safeSize = Math.min(Math.max(size == null ? 20 : size, 1), 100);
    return bookService.findPage(safePage, safeSize);
}
~~~

Server phải tự giới hạn size tối đa; không tin tưởng giá trị client gửi lên. Với API cần trả cả thông tin trang, có thể định nghĩa object wrapper:

~~~graphql
type BookPage {
  content: [BookSummary!]!
  page: Int!
  size: Int!
  hasNext: Boolean!
}

type Query {
  bookPage(page: Int = 0, size: Int = 20): BookPage!
}
~~~

Ví dụ Java DTO:

~~~java
public record BookPage(
        List<BookSummary> content,
        int page,
        int size,
        boolean hasNext) {
}
~~~

Wrapper giúp client biết còn trang tiếp theo hay không mà không phải tải toàn bộ collection. Với dữ liệu thay đổi thường xuyên hoặc cần điều hướng ổn định, cursor pagination/connection pattern có thể phù hợp hơn offset pagination.

Không nên mặc định Page<T> của Spring Data là GraphQL list. Page<T> là một object chứa nội dung và metadata phân trang; nếu schema cần list thuần, trả page.getContent(). Nếu muốn expose metadata, hãy thiết kế GraphQL object wrapper và DTO rõ ràng.

## Collection return type và reactive type

Trong Spring for GraphQL, resolver có thể trả kết quả đồng bộ hoặc reactive tùy stack của ứng dụng. Cần phân biệt một collection đã được materialize với một publisher phát dữ liệu:

| Kiểu trả về | Ý nghĩa |
| --- | --- |
| List<Book> | Danh sách đã có sẵn khi phương thức trả về |
| Collection<Book> | Tập hợp đã có sẵn, không nhất thiết cam kết List |
| Mono<List<Book>> | Một kết quả bất đồng bộ chứa toàn bộ danh sách |
| Flux<Book> | Publisher phát nhiều phần tử theo mô hình reactive |

Với Query field cần một danh sách, List<T> là lựa chọn đơn giản khi dữ liệu đã được tải đồng bộ. Nếu service reactive, dùng reactive return type được Spring for GraphQL hỗ trợ và bảo đảm các thao tác bên dưới cũng non-blocking. Với Subscription, Flux<T> thường biểu diễn luồng sự kiện theo thời gian; semantics này khác với một collection được trả về một lần.

Không gọi block() để ép Mono hoặc Flux thành collection trong resolver WebFlux. Việc block có thể chặn event loop và làm mất lợi ích reactive. Cũng không giả định Flux và List có cùng semantics; hãy kiểm thử query và subscription theo đúng transport và kiểu operation của ứng dụng.

## Những kiểu trả về cần cân nhắc

Một số kiểu Java không phải lựa chọn tốt cho GraphQL list:

- **Stream:** là luồng duyệt một lần và có thể cần đóng tài nguyên. Hãy materialize thành List trong service hoặc dùng reactive publisher được hỗ trợ.
- **Iterator:** chỉ duyệt theo trạng thái hiện tại và có thể bị tiêu thụ một lần. List thường rõ ràng hơn.
- **Map:** GraphQL thường xử lý như object có field theo key, không phải list các phần tử. Nếu cần danh sách, trả Collection; nếu cần object có cấu trúc, định nghĩa object type rõ ràng.
- **Page hoặc Slice:** chứa metadata phân trang. Chuyển thành list hoặc GraphQL wrapper thay vì coi nó là list thuần.
- **Entity collection lazy:** có thể phát sinh truy vấn bất ngờ hoặc lỗi khi persistence context đã đóng. Chuyển DTO hoặc tải quan hệ có chủ đích.

## Kiểm thử collection return type

Có thể dùng GraphQlTester để xác nhận field trả về list và các phần tử được phân giải đúng:

~~~java
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
    .entityList(BookSummary.class)
    .hasSize(2);
~~~

Nên kiểm thử:

- Collection có nhiều phần tử và thứ tự đúng.
- Collection rỗng trả về [].
- Giá trị null ở field list và null element theo đúng nullability của SDL.
- Set hoặc nguồn dữ liệu không có thứ tự được sắp xếp ổn định trước khi trả về.
- Nested collection hoạt động và không tạo N+1 ngoài dự kiến.
- Pagination giới hạn page size và trả đúng metadata.
- Reactive publisher được xử lý đúng với query hoặc subscription tương ứng.

Khi kiểm tra nullability, hãy tạo test riêng cho từng trường hợp vì GraphQL có thể đẩy null lên parent theo quy tắc propagation. Chỉ kiểm tra số phần tử là chưa đủ để xác nhận hợp đồng [Book!]! được tuân thủ.

## Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Field list trả null | Resolver hoặc service trả null | Trả collection rỗng nếu không có kết quả |
| GraphQL error khi có phần tử null | SDL khai báo phần tử non-null | Loại bỏ hoặc xử lý phần tử null trước khi trả về |
| Thứ tự response thay đổi | Dùng Set hoặc query không có ORDER BY | Quy định sort và trả List có thứ tự |
| Lỗi lazy initialization | Entity relation được đọc sau khi transaction đóng | Dùng DTO/projection hoặc tải quan hệ trong transaction |
| Nhiều query cho từng phần tử | Resolver con gọi repository riêng | Dùng @BatchMapping hoặc DataLoader |
| Response quá lớn | Trả toàn bộ collection không phân trang | Thêm pagination và giới hạn kích thước |
| Dùng Page như list | Nhầm wrapper phân trang với collection | Trả content hoặc định nghĩa GraphQL page type |
| Event loop bị chặn | Block reactive publisher | Giữ pipeline reactive xuyên suốt |

## Nguyên tắc thiết kế collection return type

Khi thiết kế field trả về danh sách trong Spring for GraphQL, hãy áp dụng:

1. **Khai báo list và nullability rõ ràng.** Phân biệt list nullable, phần tử nullable và danh sách rỗng.
2. **Ưu tiên List khi cần thứ tự.** GraphQL response giữ thứ tự mà resolver trả về.
3. **Trả collection rỗng khi không có dữ liệu.** Đừng dùng null thay cho danh sách không có phần tử nếu schema không yêu cầu như vậy.
4. **Dùng DTO hoặc projection.** Kiểm soát dữ liệu công khai và tránh phụ thuộc vào entity lazy.
5. **Batch quan hệ lồng nhau.** Dùng @BatchMapping hoặc DataLoader để hạn chế N+1.
6. **Phân trang danh sách lớn.** Giới hạn page size và cân nhắc cursor pagination khi phù hợp.
7. **Chọn đúng kiểu đồng bộ hoặc reactive.** Không block publisher trong ứng dụng reactive.
8. **Kiểm thử null propagation và thứ tự.** Response đúng số lượng chưa đủ; cần kiểm tra cả hợp đồng list.

Collection return type kết nối danh sách kết quả trong Java với list type trong GraphQL. SDL quy định cấu trúc và nullability; resolver cung cấp collection; GraphQL runtime phân giải từng phần tử và giữ thứ tự kết quả. Khi chọn List có thứ tự, trả DTO phù hợp, xử lý collection rỗng, batch các quan hệ và phân trang dữ liệu lớn, API sẽ dễ dự đoán và vận hành hiệu quả hơn.
