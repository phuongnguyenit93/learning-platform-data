# List source objects

Trong GraphQL, một field lồng nhau thường được resolve cho từng object cha. Nếu query trả về danh sách nhiều Book và client chọn Author của mỗi Book, resolver thông thường nhận một Book ở mỗi lần gọi. **@BatchMapping** thay đổi cách nhận dữ liệu: handler nhận một danh sách source object để tải quan hệ theo nhóm.

Danh sách này không phải argument do client gửi. Nó là các object cha mà GraphQL Java cần resolve cho cùng một field trong một đợt batch. Spring for GraphQL dùng cơ chế DataLoader phía dưới để gom những lần yêu cầu field, gọi batch handler với danh sách source object rồi phân phối kết quả về đúng field của từng object.

Bài này tập trung vào ý nghĩa của tham số **List<Source>** trong @BatchMapping, cách xác định source type, cách trả kết quả bằng Map hoặc List, bảo toàn quan hệ giữa đầu vào và đầu ra, xử lý quan hệ một-nhiều, giới hạn kích thước batch và kiểm thử.

## 1. Source object là gì?

Source object là giá trị được trả về từ field cha và trở thành đầu vào để resolve field con.

Ví dụ schema:

~~~graphql
type Query {
  books(first: Int = 20): [Book!]!
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

Root resolver:

~~~java
@QueryMapping
public List<Book> books(@Argument Integer first) {
    return bookService.findFirst(first);
}
~~~

Khi client gửi:

~~~graphql
query {
  books(first: 3) {
    id
    title
    author {
      id
      name
    }
  }
}
~~~

Field Query.books trả về ba object Book. Mỗi object Book là source object cho field Book.author.

Với resolver thông thường:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

Method nhận một Book mỗi lần gọi. Nếu có ba Book, method có thể được gọi ba lần. Nếu mỗi lần gọi đều truy vấn database, ứng dụng có thể gặp N+1.

## 2. List source objects trong @BatchMapping

Spring for GraphQL cung cấp **@BatchMapping** để gom nhiều source object cần resolve cùng một field. Thay vì nhận một Book, handler nhận List<Book>:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> author(List<Book> books) {
    // Tải Author cho cả nhóm Book
    return authorService.findAuthorsForBooks(books);
}
~~~

Tham số **List<Book> books** có ý nghĩa:

- Mỗi phần tử là một source object cho field Book.author.
- Danh sách được framework gom từ những lần resolve field cần batch.
- Handler có thể lấy các khóa cần thiết từ tất cả Book.
- Handler tải dữ liệu liên quan theo nhóm.
- Kết quả được ánh xạ lại cho từng source Book.

Danh sách này không phải một argument như **ids: [ID!]!** trong SDL. Client không gửi List<Book> vào handler. Spring for GraphQL cung cấp nó từ GraphQL execution thông qua batch loader.

### Sơ đồ xử lý

~~~mermaid
flowchart TD
    A[Query.books] --> B[Danh sách Book]
    B --> C1[Book 1 cần Author]
    B --> C2[Book 2 cần Author]
    B --> C3[Book 3 cần Author]
    C1 --> D[DataLoader gom source objects]
    C2 --> D
    C3 --> D
    D --> E[@BatchMapping List<Book>]
    E --> F[Batch query Authors]
    F --> G[Map hoặc List kết quả]
    G --> H[Phân phối Author cho từng Book]
    H --> I[GraphQL response]
~~~

Với một batch gồm ba Book, batch handler được gọi một lần cho nhóm đó thay vì gọi resolver riêng ba lần. Nếu giới hạn kích thước batch hoặc execution tạo ra nhiều đợt dispatch, handler có thể được gọi nhiều lần; không nên giả định một query luôn tạo đúng một lần gọi batch.

## 3. So sánh source object và argument của client

Hai loại List có thể xuất hiện trong chữ ký handler nhưng mang ý nghĩa khác nhau.

SDL:

~~~graphql
type Query {
  booksByIds(ids: [ID!]!): [Book!]!
}
~~~

Handler root:

~~~java
@QueryMapping
public List<Book> booksByIds(@Argument("ids") List<String> ids) {
    return bookService.findAllByIds(ids);
}
~~~

Ở đây **List<String> ids** là argument do client gửi và được đánh dấu bằng **@Argument**.

Trong batch handler:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> author(List<Book> books) {
    return authorService.findAuthorsForBooks(books);
}
~~~

**List<Book> books** là danh sách source object do Spring for GraphQL gom lại. Nó không phải argument của field Book.author.

| Chữ ký tham số | Nguồn dữ liệu |
|---|---|
| **@Argument("ids") List<String> ids** | Argument từ GraphQL operation |
| **List<Book> books** trong @BatchMapping | Source object được gom từ field cha |
| **Book book** trong @SchemaMapping | Một source object cho một lần resolve |

Phân biệt đúng nguồn dữ liệu giúp tránh thêm annotation @Argument sai chỗ hoặc hiểu nhầm rằng client phải gửi danh sách object cha.

## 4. Spring suy ra source type và field như thế nào?

Trong @BatchMapping, Spring có thể suy ra type chứa field từ generic type của tham số source list và suy ra tên field từ tên method.

Ví dụ:

~~~java
@BatchMapping
public Map<Book, Author> author(List<Book> books) {
    return authorService.findAuthorsForBooks(books);
}
~~~

Framework có thể suy ra:

- Source type là **Book** từ List<Book>.
- Field là **author** từ tên method.

Để mapping rõ ràng hơn, có thể chỉ định tường minh:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> loadAuthors(List<Book> books) {
    return authorService.findAuthorsForBooks(books);
}
~~~

Tên method Java không cần giống tên field khi đã khai báo field rõ ràng.

Nếu một controller chứa nhiều batch mapping cho cùng một source type, có thể dùng cách khai báo tường minh để người đọc dễ nhận biết mapping nào phụ trách field nào.

## 5. Trả kết quả bằng Map<Source, Value>

Một cách phổ biến là trả Map trong đó key là source object, value là giá trị của field cần resolve.

Ví dụ model:

~~~java
public record Book(
        String id,
        String title,
        String authorId) {
}

public record Author(
        String id,
        String name) {
}
~~~

Batch mapping:

~~~java
@Controller
public class BookBatchController {

    private final AuthorService authorService;

    public BookBatchController(AuthorService authorService) {
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

        Map<Book, Author> result = new HashMap<>();
        for (Book book : books) {
            result.put(book, authorsById.get(book.authorId()));
        }
        return result;
    }
}
~~~

Batch handler thực hiện hai bước:

1. Lấy authorId từ toàn bộ Book và loại bỏ ID trùng.
2. Truy vấn Author theo danh sách ID, sau đó ánh xạ kết quả về từng Book.

Ví dụ SQL phía service có thể dùng:

~~~sql
SELECT id, name
FROM author
WHERE id IN (?, ?, ?);
~~~

Nếu có ba Book nhưng chỉ tham chiếu hai Author khác nhau, batch query chỉ cần tải hai ID. Mỗi Book vẫn nhận đúng Author tương ứng từ Map kết quả.

### Map key phải tương ứng với source object

Với dạng Map<Book, Author>, key cần tương ứng với source Book mà batch loader đã nhận. Khi dùng class Java thông thường hoặc JPA entity, cần chú ý equals và hashCode để key hoạt động ổn định.

Java record tự cung cấp equals/hashCode dựa trên component. Với entity có equals/hashCode dựa trên ID được sinh sau khi persist, cần hiểu rõ hành vi trước khi dùng làm Map key. Nếu không muốn phụ thuộc vào equality của entity, có thể trả List theo đúng thứ tự source input.

### Không phụ thuộc thứ tự database trả về

Database không bảo đảm thứ tự của kết quả nếu câu SQL không có ORDER BY. Không nên lấy danh sách Author trả về rồi giả định phần tử thứ nhất ứng với Book thứ nhất.

Hãy tạo Map theo ID hoặc source object để ánh xạ chính xác, bất kể database trả kết quả theo thứ tự nào.

## 6. Trả kết quả bằng List theo đúng thứ tự source

Batch handler cũng có thể trả về List. Khi dùng dạng này, phần tử ở vị trí i phải là kết quả tương ứng với source object ở vị trí i trong danh sách đầu vào.

Ví dụ:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public List<Author> author(List<Book> books) {
    List<String> authorIds = books.stream()
            .map(Book::authorId)
            .distinct()
            .toList();

    Map<String, Author> authorsById =
            authorService.findAllByIds(authorIds);

    List<Author> result = new ArrayList<>(books.size());
    for (Book book : books) {
        result.add(authorsById.get(book.authorId()));
    }
    return result;
}
~~~

Giả sử source list là:

| Vị trí | Source Book | authorId |
|---:|---|---|
| 0 | Book A | author-01 |
| 1 | Book B | author-02 |
| 2 | Book C | author-01 |

Batch result phải giữ đúng vị trí:

| Vị trí | Kết quả phải trả |
|---:|---|
| 0 | Author của Book A |
| 1 | Author của Book B |
| 2 | Author của Book C |

Book A và Book C có cùng authorId nên có thể dùng chung một Author object trong kết quả, nhưng vẫn phải xuất hiện ở cả hai vị trí.

Không được:

- Sort danh sách Author theo tên rồi trả trực tiếp.
- Bỏ phần tử khi không tìm thấy Author.
- Chỉ trả những kết quả khác null.
- Trả List có số phần tử khác số source object.

Nếu bỏ phần tử ở giữa, các giá trị phía sau sẽ bị ghép nhầm với parent khác. Khi cần xử lý trường hợp không tìm thấy liên kết, hãy giữ vị trí bằng một phần tử null hoặc dùng Map có key rõ ràng.

### Chọn Map hay List?

| Tiêu chí | Map<Source, Value> | List<Value> |
|---|---|---|
| Ghép kết quả | Theo source key | Theo vị trí |
| Phụ thuộc thứ tự | Không phụ thuộc thứ tự result | Bắt buộc giữ thứ tự input |
| Yêu cầu equals/hashCode | Cần key hoạt động ổn định | Không cần dùng source làm Map key |
| Trường hợp thiếu dữ liệu | Có thể không có key hoặc map null | Cần giữ vị trí tương ứng |
| Đọc code | Thể hiện rõ quan hệ source-result | Gọn khi dễ bảo toàn thứ tự |

Nếu kết quả query có thứ tự không xác định hoặc entity không có equality ổn định, Map thường dễ kiểm soát hơn. Nếu có thể tạo kết quả theo đúng thứ tự source list, List là lựa chọn đơn giản.

## 7. Batch mapping cho quan hệ một-nhiều

Không chỉ quan hệ Book.author mới có thể batch. Một Book có thể có nhiều Review:

~~~graphql
type Book {
  id: ID!
  title: String!
  reviews: [Review!]!
}

type Review {
  id: ID!
  content: String!
}
~~~

Batch handler có thể trả Map<Book, List<Review>>:

~~~java
@BatchMapping(typeName = "Book", field = "reviews")
public Map<Book, List<Review>> reviews(List<Book> books) {
    List<String> bookIds = books.stream()
            .map(Book::id)
            .toList();

    Map<String, List<Review>> reviewsByBookId =
            reviewService.findAllByBookIds(bookIds);

    Map<Book, List<Review>> result = new HashMap<>();
    for (Book book : books) {
        List<Review> reviews = reviewsByBookId.getOrDefault(
                book.id(),
                List.of());
        result.put(book, reviews);
    }
    return result;
}
~~~

Service có thể tải review của nhiều Book trong một truy vấn:

~~~sql
SELECT id, book_id, content
FROM review
WHERE book_id IN (?, ?, ?)
ORDER BY book_id, id;
~~~

Sau đó nhóm Review theo bookId và trả danh sách cho từng source Book.

Với quan hệ một-nhiều, nên trả danh sách rỗng khi parent không có phần tử con nếu SDL khai báo list non-null. Ví dụ **[Review!]!** yêu cầu field luôn có list và không có phần tử null. Danh sách rỗng là kết quả hợp lệ.

Nếu field schema cho phép null list, quyết định trả null hay list rỗng phải phản ánh semantics của domain. Không nên dùng null và empty list thay thế nhau tùy tiện.

## 8. Batch size và nhiều đợt gọi handler

Không nên mặc định toàn bộ source object của một operation luôn được đưa vào một List duy nhất. DataLoader có thể dispatch theo từng đợt và có thể giới hạn kích thước batch.

**@BatchMapping** hỗ trợ thuộc tính **maxBatchSize** để giới hạn số source object trong một batch:

~~~java
@BatchMapping(
        typeName = "Book",
        field = "author",
        maxBatchSize = 100)
public Map<Book, Author> author(List<Book> books) {
    return authorService.findAuthorsForBooks(books);
}
~~~

Với cấu hình này, mỗi lần gọi batch handler nhận tối đa 100 source object. Nếu có nhiều hơn, loader có thể chia thành nhiều batch.

Giới hạn batch có ích khi:

- Database giới hạn số bind parameters.
- Batch query quá lớn gây tăng memory hoặc thời gian xử lý.
- Service phía sau có giới hạn số key trong một request.
- Cần kiểm soát kích thước payload nội bộ giữa GraphQL và data layer.

Batch size quá nhỏ làm tăng số lần gọi batch. Batch size quá lớn có thể tạo câu query lớn và tiêu tốn bộ nhớ. Nên chọn dựa trên giới hạn database, kích thước dữ liệu và số liệu đo được.

Nếu không chỉ định maxBatchSize, hành vi mặc định phụ thuộc cấu hình DataLoader và phiên bản thư viện. Hãy kiểm tra dependency Spring for GraphQL đang sử dụng trước khi dựa vào một giới hạn cụ thể.

## 9. Batch handler có thể chạy bất đồng bộ

Spring for GraphQL hỗ trợ kiểu trả về bất đồng bộ và reactive cho handler method. Batch handler có thể tải dữ liệu từ service bất đồng bộ nếu tầng data access hỗ trợ.

Ví dụ minh họa với Mono:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Mono<Map<Book, Author>> author(List<Book> books) {
    List<String> authorIds = books.stream()
            .map(Book::authorId)
            .distinct()
            .toList();

    return authorService.findAllByIdsAsync(authorIds)
            .map(authorsById -> {
                Map<Book, Author> result = new HashMap<>();
                for (Book book : books) {
                    result.put(
                            book,
                            authorsById.get(book.authorId()));
                }
                return result;
            });
}
~~~

Ví dụ này giả định service trả về **Mono<Map<String, Author>>**. Batch result chỉ được hoàn tất khi service hoàn thành. Cần chọn kiểu reactive phù hợp với stack của ứng dụng và tránh chặn thread bằng cách gọi blocking repository trong reactive pipeline.

Nếu dùng JPA/JDBC blocking, một method đồng bộ có thể phù hợp hơn; không nên bọc một lời gọi blocking trong Mono chỉ để có vẻ reactive.

## 10. Xử lý source list rỗng và dữ liệu thiếu

Trong thực tế, batch handler nên xử lý rõ trường hợp không có source object hoặc không có dữ liệu liên quan.

### Source list rỗng

Nếu không có parent nào yêu cầu field, thông thường batch loader không cần thực hiện truy vấn. Nếu handler được gọi với list rỗng trong một tình huống cụ thể, không nên gọi repository với danh sách rỗng khi SQL dialect hoặc API service không hỗ trợ.

Có thể bảo vệ:

~~~java
if (books.isEmpty()) {
    return Map.of();
}
~~~

### Không tìm thấy child object

Giả sử một Book tham chiếu authorId không còn tồn tại. Có hai lựa chọn chính:

- Nếu field Book.author nullable, trả null cho Book đó.
- Nếu field Book.author non-null, dữ liệu thiếu là lỗi cần được xử lý theo domain và GraphQL nullability.

Với Map, có thể không thêm key tương ứng hoặc thêm key với null value tùy contract và cách loader xử lý. Với List, phải giữ phần tử null đúng vị trí nếu field cho phép.

Với quan hệ một-nhiều, không có Review thường được biểu diễn bằng empty list.

Không nên bỏ source object khỏi kết quả. Batch loader cần có khả năng ánh xạ kết quả về từng key đầu vào.

## 11. Tránh giả định thứ tự kết quả của repository

Một lỗi phổ biến là lấy danh sách source IDs, gọi repository rồi trả nguyên danh sách kết quả:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public List<Author> author(List<Book> books) {
    List<String> ids = books.stream()
            .map(Book::authorId)
            .toList();

    return authorRepository.findAllById(ids);
}
~~~

Đoạn code này không an toàn nếu repository không bảo đảm kết quả có cùng thứ tự với danh sách IDs đầu vào. Nhiều API repository chỉ trả về các entity tìm thấy và không cam kết thứ tự.

Cách an toàn là tạo Map theo ID:

~~~java
Map<String, Author> authorsById =
        authorService.findAllByIds(ids);

List<Author> result = new ArrayList<>();
for (Book book : books) {
    result.add(authorsById.get(book.authorId()));
}
return result;
~~~

Hoặc trả Map<Book, Author>:

~~~java
Map<Book, Author> result = new HashMap<>();
for (Book book : books) {
    result.put(book, authorsById.get(book.authorId()));
}
return result;
~~~

Hai cách đều giữ đúng quan hệ giữa parent và child dù database trả về theo thứ tự bất kỳ.

## 12. BatchMapping và DataLoader liên hệ với nhau ra sao?

**@BatchMapping** là cách khai báo batch field resolver ở mức annotated controller. Spring for GraphQL đăng ký batch loader phía dưới thông qua cơ chế DataLoader.

Khái quát:

| Thành phần | Trách nhiệm |
|---|---|
| Source object | Object cha cần resolve field con |
| List<Source> | Nhóm source object được đưa vào batch handler |
| @BatchMapping | Khai báo field mapping và batch method |
| DataLoader | Gom các yêu cầu load trong execution và điều phối dispatch |
| Batch method | Tải dữ liệu cho nhóm source object |
| Map/List result | Ghép giá trị trả về với từng source |

Khi chỉ cần batch một field đơn giản, @BatchMapping giảm lượng code đăng ký DataLoader thủ công. Nếu cần chia sẻ loader giữa nhiều controller, dùng key khác source object, custom options hoặc logic dispatch phức tạp, có thể đăng ký DataLoader trực tiếp qua **BatchLoaderRegistry**.

BatchMapping không có nghĩa mọi truy vấn database của controller tự động được gom. Chỉ các field được ánh xạ qua batch method mới dùng cơ chế batch đó.

## 13. Chọn @BatchMapping hay @SchemaMapping?

Hai annotation phục vụ các kiểu handler khác nhau:

| Tiêu chí | @SchemaMapping | @BatchMapping |
|---|---|---|
| Source parameter | Một source object | List source objects |
| Cách tải dữ liệu | Thường xử lý từng parent | Xử lý một nhóm parent |
| Phù hợp | Property hoặc logic riêng cho một object | Quan hệ cần tải theo nhóm |
| N+1 | Có thể xảy ra nếu mỗi lần gọi truy vấn riêng | Giúp gom tải dữ liệu |
| Kết quả | Một field value | Map source-to-value hoặc List theo thứ tự |

Ví dụ @SchemaMapping:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorService.findById(book.authorId());
}
~~~

Ví dụ @BatchMapping:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> author(List<Book> books) {
    return authorService.findAuthorsForBooks(books);
}
~~~

Không phải mọi field đều nên batch. Nếu field là property có sẵn trên source object, default property fetcher có thể đủ. Nếu field cần tải dữ liệu theo từng parent và có thể gom theo nhóm, @BatchMapping thường phù hợp hơn.

## 14. Kiểm thử batch method nhận List source objects

GraphQlTester có thể kiểm tra response của field được batch. Để kiểm tra batch behavior, cần thêm spy/mock hoặc query counter cho service được gọi bên trong batch method.

Ví dụ operation:

~~~graphql
query {
  books(first: 3) {
    id
    title
    author {
      id
      name
    }
  }
}
~~~

Test response:

~~~java
@SpringBootTest
class BookBatchMappingTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void shouldResolveAuthorsForAllBooks() {
        graphQlTester.document("""
                query {
                    books(first: 3) {
                        title
                        author {
                            name
                        }
                    }
                }
                """)
            .execute()
            .path("books")
            .entityList(BookWithAuthorView.class)
            .hasSize(3);
    }
}
~~~

Để xác nhận batch method nhận nhiều source object, có thể:

1. Mock AuthorService và capture danh sách author IDs.
2. Xác nhận service được gọi theo batch thay vì một lần cho mỗi Book.
3. Kiểm tra IDs trùng được xử lý đúng.
4. Kiểm tra kết quả trả về đúng Book tương ứng.
5. Kiểm tra trường hợp database trả kết quả không theo thứ tự input.
6. Kiểm tra child không tồn tại và nullability của field.
7. Kiểm tra quan hệ một-nhiều trả empty list khi không có child.
8. Kiểm tra maxBatchSize nếu ứng dụng cấu hình giới hạn.
9. Kiểm tra async batch method hoàn tất đúng và không block reactive event loop.
10. Đo SQL query count để bảo đảm không còn truy vấn riêng cho từng source.

Chỉ kiểm tra GraphQL response chưa đủ để chứng minh N+1 đã được loại bỏ. Batch method có thể vẫn gọi repository trong vòng lặp; cần kiểm tra số lần service/repository hoặc số câu SQL thực tế.

## 15. Những lỗi thường gặp với List source objects

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Method nhận List rỗng hoặc không được gọi | Field không được client chọn hoặc mapping không khớp | Kiểm tra selection set, typeName và field |
| Nhầm List source với List argument | Không phân biệt @BatchMapping và @Argument | Source list do framework cung cấp; argument dùng @Argument |
| Kết quả Author gắn nhầm Book | Trả List không giữ thứ tự input | Dựng kết quả theo source list hoặc dùng Map |
| Thiếu kết quả cho một source | Bỏ phần tử khi child không tồn tại | Giữ vị trí null hoặc map source với null |
| Map không tìm được source key | equals/hashCode của source object không ổn định | Dùng equality ổn định hoặc trả List có thứ tự |
| Vẫn còn N+1 | Batch method gọi service/repository trong vòng lặp | Gom key và truy vấn một lần theo nhóm |
| Một batch quá lớn | Không giới hạn số key | Cấu hình maxBatchSize và đo thực tế |
| Database result sai thứ tự | Giả định repository trả theo thứ tự input | Ánh xạ qua ID trước khi dựng output |
| One-to-many trả null ngoài ý muốn | Không có child nhưng không tạo empty list | Dùng empty list nếu schema/domain yêu cầu |
| Batch handler không được dùng | Có DataFetcher khác đã đăng ký cho cùng field | Kiểm tra mapping và runtime wiring |

## 16. Quy trình triển khai List source objects

Khi chuyển một field resolver sang batch:

1. Xác định object type cha và field quan hệ cần resolve.
2. Xác nhận field được client chọn cho nhiều source object trong cùng execution.
3. Viết method **@BatchMapping** nhận **List<Source>**.
4. Chỉ định typeName và field tường minh nếu tên không thể suy ra rõ ràng.
5. Trích xuất key từ toàn bộ source object.
6. Loại bỏ key trùng nếu service/database có thể tải theo tập ID.
7. Truy vấn dữ liệu theo batch, không gọi repository trong vòng lặp.
8. Trả Map<Source, Value> hoặc List<Value> giữ đúng thứ tự source.
9. Xử lý child thiếu, nullability và quan hệ một-nhiều.
10. Chọn maxBatchSize theo giới hạn thực tế khi cần.
11. Viết GraphQlTester và kiểm tra số lần gọi service/SQL.
12. Đo lại latency, query count và memory với nhiều kích thước danh sách.

Tham số List source objects là điểm cốt lõi của @BatchMapping: nó cho batch handler biết toàn bộ parent cần resolve trong một nhóm. Spring for GraphQL gom các source object thông qua DataLoader, còn handler chịu trách nhiệm tải dữ liệu hiệu quả và ghép kết quả về đúng source. Trả Map giúp ánh xạ theo key; trả List yêu cầu giữ nguyên thứ tự và số phần tử tương ứng. Khi xử lý đúng source list, tránh truy vấn trong vòng lặp và kiểm thử query count, batch mapping có thể giảm N+1 mà vẫn giữ response đúng với schema.
