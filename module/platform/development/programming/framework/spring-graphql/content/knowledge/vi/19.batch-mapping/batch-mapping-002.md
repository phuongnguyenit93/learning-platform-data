# Batch mapping cho nested field

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vì sao resolver của nested field dễ tạo ra vấn đề N+1.
- Dùng @BatchMapping để gom việc phân giải nhiều source object thành một batch.
- Viết batch method trả về Map hoặc List đúng với contract của Spring for GraphQL.
- Hiểu cách DataLoader gom key, xử lý key trùng và lưu cache trong một lần thực thi.
- Chọn batch size và xử lý quan hệ không tồn tại.
- Kiểm thử kết quả GraphQL và số lần truy cập service/repository.

## Nested field và vấn đề N+1

GraphQL cho phép client truy vấn field lồng nhau theo nhu cầu. Ví dụ một query lấy nhiều sách và thông tin tác giả của từng sách:

~~~graphql
type Query {
  books(first: Int!): [Book!]!
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

Client:

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

Resolver thông thường cho Book.author có thể viết:

~~~java
@Controller
public class BookFieldController {

    private final AuthorService authorService;

    public BookFieldController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.authorId()).orElse(null);
    }
}
~~~

Resolver này được gọi riêng cho từng Book. Nếu query trả về 3 sách, ứng dụng có thể chạy một truy vấn lấy danh sách sách và thêm 3 truy vấn lấy tác giả. Với 100 sách, số truy vấn có thể tăng thành 1 + 100.

Đây là vấn đề N+1: một truy vấn ban đầu lấy N object, sau đó mỗi object phát sinh thêm một truy vấn để lấy dữ liệu của nested field. GraphQL không tự động gom các lời gọi repository chỉ vì chúng nằm trong cùng một operation.

N+1 không chỉ xuất hiện ở database. Nếu resolver gọi một REST service, gRPC service hoặc một hệ thống từ xa cho từng parent object, số lượt gọi mạng cũng có thể tăng tương tự.

## @BatchMapping giải quyết vấn đề như thế nào?

Spring for GraphQL cung cấp @BatchMapping để phân giải một nested field cho nhiều source object cùng lúc. Thay vì nhận một Book và trả về một Author, batch method nhận một danh sách Book rồi trả về kết quả tương ứng cho toàn bộ danh sách.

Ví dụ:

~~~java
@Controller
public class BookFieldController {

    private final AuthorService authorService;

    public BookFieldController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public List<Author> author(List<Book> books) {
        List<String> authorIds = books.stream()
                .map(Book::authorId)
                .filter(Objects::nonNull)
                .distinct()
                .toList();

        Map<String, Author> authorsById =
                authorService.findAllByIds(authorIds).stream()
                        .collect(Collectors.toMap(
                                Author::id,
                                Function.identity()));

        return books.stream()
                .map(book -> authorsById.get(book.authorId()))
                .toList();
    }
}
~~~

Batch method nhận toàn bộ Book đang cần field author. Service truy vấn các tác giả theo một tập authorId, sau đó method tạo danh sách kết quả theo đúng thứ tự của danh sách Book đầu vào.

Với query lấy 100 sách, thay vì gọi AuthorService 100 lần, batch method có thể gọi findAllByIds một lần cho tập ID cần thiết. Số truy vấn thực tế phụ thuộc vào batch size, cách phân trang, giới hạn của database và cấu hình DataLoader.

@BatchMapping là shortcut của Spring for GraphQL để kết hợp field mapping với DataLoader. Spring đăng ký batch loader cho field và dùng nó để phân giải nested field. Bạn không cần tự tạo DataLoaderRegistry hoặc tự gọi dispatch trong trường hợp thông thường.

Không khai báo thêm một @SchemaMapping cho cùng field Book.author. @BatchMapping đã đảm nhiệm mapping field đó. Hai resolver cạnh tranh cho cùng một field sẽ gây xung đột hoặc làm cấu hình không rõ ràng.

## Quy tắc ánh xạ source và kết quả

Một batch method cần trả kết quả có thể ghép chính xác với từng source object. Spring for GraphQL hỗ trợ hai dạng kết quả phổ biến:

1. Map từ source object sang giá trị field.
2. List các giá trị field có thứ tự tương ứng với danh sách source object đầu vào.

### Trả về List theo thứ tự source

Ví dụ ở phần trước trả về List<Author>. Nếu batch method nhận:

~~~text
books = [bookA, bookB, bookC]
~~~

thì danh sách kết quả phải có cùng số phần tử và cùng thứ tự:

~~~text
authors = [authorA, authorB, authorC]
~~~

Phần tử ở vị trí i là kết quả của field author trên source object ở vị trí i. Nếu một sách không có tác giả hoặc tác giả không tồn tại mà schema cho phép, vị trí tương ứng có thể chứa null.

Không sắp xếp danh sách tác giả theo tên hoặc ID rồi trả thẳng về. DataLoader không thể biết một phần tử đã bị chuyển sang vị trí nào nếu kết quả dạng List không còn giữ thứ tự nguồn.

Ví dụ an toàn là truy vấn theo tập ID để tạo Map tra cứu, sau đó dựng lại List theo danh sách Book ban đầu. Cách này vừa tận dụng truy vấn theo lô vừa bảo toàn thứ tự.

### Trả về Map theo source object

Khi muốn tránh phụ thuộc vào thứ tự, có thể trả Map<Book, Author>:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> author(List<Book> books) {
    List<String> authorIds = books.stream()
            .map(Book::authorId)
            .filter(Objects::nonNull)
            .distinct()
            .toList();

    Map<String, Author> authorsById =
            authorService.findAllByIds(authorIds).stream()
                    .collect(Collectors.toMap(
                            Author::id,
                            Function.identity()));

    Map<Book, Author> result = new HashMap<>();
    for (Book book : books) {
        Author author = book.authorId() == null
                ? null
                : authorsById.get(book.authorId());
        if (author != null) {
            result.put(book, author);
        }
    }
    return result;
}
~~~

Key của Map là source object Book nhận vào batch method; value là Author tương ứng. Với mapped batch loader, key không có trong Map sẽ được xem là không có giá trị tương ứng và được phân giải thành null.

Khi dùng Map, cần bảo đảm kiểu key có quy tắc equals/hashCode ổn định. Nếu Book là JPA entity, hãy cẩn thận với equals/hashCode dựa trên ID chưa được gán hoặc proxy entity. Nếu không chắc chắn về equality của source object, dạng List giữ nguyên thứ tự thường dễ kiểm soát hơn.

Không trả Map<String, Author> chỉ vì service tra cứu theo authorId. Batch mapping cần kết quả gắn với từng source object Book, không phải chỉ với ID của tác giả. Có thể dùng Map<String, Author> làm cấu trúc tra cứu trung gian như ví dụ, rồi chuyển thành Map<Book, Author> hoặc List<Author> ở bước cuối.

## Dữ liệu quan hệ không tồn tại

Trong ví dụ, field Book.author được khai báo nullable:

~~~graphql
type Book {
  id: ID!
  title: String!
  author: Author
}
~~~

Nếu Book không có authorId hoặc tác giả đã bị xóa, batch method có thể trả null cho field đó. Với dạng List, hãy giữ null ở đúng vị trí source tương ứng. Với dạng Map, có thể bỏ qua key không có kết quả để DataLoader phân giải giá trị thiếu thành null.

Nếu schema khai báo author: Author!, server phải bảo đảm mọi Book được trả về đều có một Author hợp lệ. Khi batch method không tìm thấy tác giả cho một sách, kết quả null sẽ vi phạm non-null và GraphQL áp dụng null propagation. Không nên khai báo non-null chỉ vì phần lớn bản ghi hiện có đều có tác giả.

Hãy phân biệt:

- Không có quan hệ hợp lệ: trả null nếu schema và nghiệp vụ cho phép.
- Repository hoặc dịch vụ phụ thuộc gặp lỗi: phát sinh lỗi để GraphQL xử lý, không chuyển lỗi hạ tầng thành null.
- Dữ liệu vi phạm invariant: ghi nhận và xử lý như lỗi dữ liệu, không âm thầm bỏ qua nếu điều đó che giấu sự cố.

## BatchMapping và DataLoader

DataLoader là cơ chế gom nhiều lần yêu cầu dữ liệu thành một batch. Khi các resolver yêu cầu author cho nhiều Book, DataLoader ghi nhận các key cần tải. Ở thời điểm dispatch của GraphQL execution, batch loader được gọi với tập key đã tích lũy và trả về kết quả tương ứng.

Với @BatchMapping, Spring for GraphQL tạo và đăng ký DataLoader cần thiết cho field. Luồng tổng quát:

~~~mermaid
flowchart TD
    A[Query lấy danh sách Book] --> B[GraphQL phân giải Book.author]
    B --> C[DataLoader ghi nhận từng Book key]
    C --> D[GraphQL dispatch batch]
    D --> E[@BatchMapping nhận List<Book>]
    E --> F[Thu thập authorId duy nhất]
    F --> G[AuthorService truy vấn theo lô]
    G --> H[Tạo kết quả theo Book]
    H --> I[DataLoader hoàn tất từng field]
    I --> J[GraphQL tạo response]
~~~

DataLoader còn hỗ trợ cache theo key trong phạm vi một lần thực thi. Nếu nhiều nhánh của cùng operation cần cùng một key, DataLoader có thể tái sử dụng kết quả đã tải thay vì gọi batch loader lặp lại. Cơ chế cache này thường có phạm vi theo request/execution, không nên thay bằng một cache toàn cục chứa dữ liệu phụ thuộc người dùng hoặc tenant.

Việc gom batch và cache giúp giảm số lần truy cập dữ liệu, nhưng không thay thế thiết kế query hiệu quả. Batch method vẫn cần truy vấn đúng tập dữ liệu, tránh tải quá nhiều cột hoặc bản ghi không cần thiết.

## Xử lý ID trùng và null

Nhiều Book có thể cùng một authorId. Khi truy vấn repository, nên loại ID trùng để không tải cùng tác giả nhiều lần:

~~~java
List<String> authorIds = books.stream()
        .map(Book::authorId)
        .filter(Objects::nonNull)
        .distinct()
        .toList();
~~~

DataLoader có thể xử lý key trùng trong quá trình load và cache, nhưng batch method vẫn nên tạo truy vấn theo tập ID duy nhất để giảm công việc ở tầng repository. Kết quả cuối cùng vẫn phải được ghép cho từng Book, kể cả khi nhiều Book cùng tham chiếu một Author.

Không đưa null vào danh sách ID truy vấn. Nếu field quan hệ nullable, hãy bỏ qua các source không có ID khi tạo tập key và trả null cho source tương ứng.

Trường hợp danh sách source rỗng thường không cần gọi repository. Batch method có thể trả collection rỗng tương ứng.

## Giới hạn kích thước batch

Một batch rất lớn có thể vượt giới hạn số parameter của database hoặc tạo truy vấn quá nặng. @BatchMapping hỗ trợ thuộc tính maxBatchSize để giới hạn số source key trong một batch:

~~~java
@BatchMapping(
        typeName = "Book",
        field = "author",
        maxBatchSize = 100)
public List<Author> author(List<Book> books) {
    // Truy vấn và trả kết quả theo đúng thứ tự books.
}
~~~

Khi số key vượt giới hạn, DataLoader chia thành nhiều batch nhỏ. Ví dụ 250 source với maxBatchSize là 100 có thể được xử lý thành các batch 100, 100 và 50. Đây là giới hạn cho mỗi lần batch dispatch, không phải giới hạn phân trang của root query.

Chọn maxBatchSize dựa trên giới hạn database, kích thước câu SQL, độ trễ dịch vụ phụ thuộc và lượng dữ liệu trả về. Không đặt một giá trị rất lớn chỉ để giảm số batch; batch quá lớn có thể làm tăng bộ nhớ, thời gian truy vấn và tải hệ thống.

Nếu service bulk query có giới hạn riêng, hãy bảo đảm maxBatchSize tương thích. Với một batch cần chia tiếp theo giới hạn repository, có thể xử lý chunk bên trong service và ghép kết quả trước khi trả về batch method.

## Batch nhiều nested field

Một schema có thể có nhiều quan hệ cần tải theo lô. Ví dụ Book có author và publisher:

~~~graphql
type Book {
  id: ID!
  title: String!
  author: Author
  publisher: Publisher
}
~~~

Có thể khai báo hai batch mapping riêng:

~~~java
@Controller
public class BookRelationController {

    private final AuthorService authorService;
    private final PublisherService publisherService;

    public BookRelationController(
            AuthorService authorService,
            PublisherService publisherService) {
        this.authorService = authorService;
        this.publisherService = publisherService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public List<Author> author(List<Book> books) {
        // Bulk load authors và giữ đúng thứ tự source.
        return authorService.findForBooks(books);
    }

    @BatchMapping(typeName = "Book", field = "publisher")
    public List<Publisher> publisher(List<Book> books) {
        // Bulk load publishers và giữ đúng thứ tự source.
        return publisherService.findForBooks(books);
    }
}
~~~

Mỗi field có batch loader riêng. Nếu client chỉ chọn author, resolver publisher không cần chạy. Nếu client chọn cả hai, GraphQL có thể gom các yêu cầu cho từng field theo cơ chế DataLoader tương ứng.

Với quan hệ sâu hơn như Author.organization, có thể tạo batch mapping trên Author. Mỗi cấp nested field có thể có batch loader riêng; cần theo dõi số batch và số truy vấn trên toàn operation để tránh chỉ chuyển N+1 từ một quan hệ sang quan hệ khác.

## Khi nào dùng @BatchMapping, khi nào dùng DataLoader tường minh?

@BatchMapping phù hợp khi:

- Cần phân giải một field của object type cho nhiều source object cùng loại.
- Batch key chính là source object.
- Có thể trả kết quả dưới dạng Map<Source, Value> hoặc List<Value> theo thứ tự source.
- Muốn Spring for GraphQL tự đăng ký DataLoader cho field.

DataLoader tường minh phù hợp khi:

- Nhiều field hoặc nhiều resolver cần dùng chung một loại loader.
- Key tải dữ liệu là ID hoặc một cấu trúc khác, không phải source object.
- Cần tùy chỉnh cách đăng ký loader, context hoặc chiến lược cache.
- Cần dùng cùng batch loader ngoài một mapping đơn giản.

Ví dụ resolver dùng DataLoader được inject:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public CompletableFuture<Author> author(
        Book book,
        DataLoader<String, Author> authorLoader) {
    return authorLoader.load(book.authorId());
}
~~~

Với cách này, DataLoader có key là authorId. Ứng dụng cần đăng ký loader tương ứng bằng BatchLoaderRegistry hoặc cơ chế cấu hình DataLoader phù hợp. Không đăng ký thêm một @BatchMapping cho cùng Book.author.

Nếu chỉ cần gom source object của một field, @BatchMapping thường ngắn gọn và dễ đọc hơn. Khi key, cache hoặc việc chia sẻ loader có yêu cầu riêng, hãy cân nhắc DataLoader tường minh.

## Kiểm thử BatchMapping

Nên kiểm tra cả response và số lần batch service được gọi. Ví dụ query lấy nhiều sách:

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

Một test với GraphQlTester có thể xác minh dữ liệu nested field:

~~~java
graphQlTester.document("""
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
        """)
    .execute()
    .path("books[0].author.name")
    .entity(String.class)
    .isEqualTo("Nguyen An");
~~~

Ngoài response, dùng Mockito hoặc spy để xác minh bulk service được gọi theo batch thay vì gọi một lần cho mỗi Book. Ví dụ với một batch:

~~~java
verify(authorService, times(1))
        .findAllByIds(anyList());
~~~

Số lần gọi thực tế phụ thuộc số batch, maxBatchSize và execution. Nếu test chỉ có ba sách và maxBatchSize lớn hơn ba, kỳ vọng một lần gọi bulk service là hợp lý. Không nên viết assertion cố định một lần nếu fixture cố ý vượt giới hạn batch.

Nên kiểm thử:

1. Nhiều Book được trả về và nested author được ghép đúng.
2. Nhiều Book cùng authorId không làm sai kết quả.
3. Batch method trả List giữ đúng thứ tự source.
4. Batch method trả Map ghép đúng source object.
5. Book không có authorId hoặc author không tồn tại được xử lý thành null khi schema nullable.
6. Batch vượt maxBatchSize được chia thành nhiều lần tải phù hợp.
7. Client không chọn nested field thì batch service không bị gọi.
8. Query có nhiều nested relation chỉ gọi đúng loader cần thiết.
9. Lỗi từ bulk service trở thành GraphQL error theo chính sách ứng dụng.

Trong test slice @GraphQlTest, đưa controller chứa @BatchMapping vào context và mock service. Integration test với application context đầy đủ hữu ích để xác minh cấu hình DataLoader và repository thật.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Vẫn có N+1 sau khi thêm @BatchMapping | Batch method không được phát hiện hoặc field mapping không khớp | Kiểm tra @Controller, typeName, field và schema |
| Kết quả author bị ghép nhầm sách | List trả về không giữ thứ tự source | Dựng lại kết quả theo danh sách Book đầu vào hoặc dùng Map |
| Một số nested field luôn null | Key Map không khớp source object hoặc không tìm thấy quan hệ | Kiểm tra equals/hashCode và dữ liệu ID |
| Batch query trả nhiều kết quả trùng | Không loại ID trùng khi truy vấn bulk | Dùng distinct cho key và ghép kết quả lại cho từng source |
| Repository vẫn được gọi quá nhiều | Batch size quá nhỏ hoặc loader không gom cùng execution | Kiểm tra maxBatchSize, loader registration và execution scope |
| Query không chọn author nhưng service vẫn chạy | Có logic gọi service ngoài batch mapping | Chỉ tải nested data khi field được yêu cầu |
| Batch method và @SchemaMapping xung đột | Cùng đăng ký một field | Chỉ giữ một resolver cho field đó |
| Cache trả dữ liệu sai người dùng | Dùng cache dùng chung ngoài request cho dữ liệu phụ thuộc quyền | Giữ cache DataLoader trong execution scope và đưa tenant/user context vào chiến lược key khi cần |
| Batch vượt giới hạn database | Một batch chứa quá nhiều key | Giới hạn maxBatchSize hoặc chia chunk ở service |

## Thực hành tổng hợp

Xây dựng API thư viện có danh sách sách và hai nested relation:

1. Query books trả về danh sách Book có phân trang.
2. Book.author được phân giải bằng @BatchMapping.
3. Book.publisher cũng được phân giải bằng một @BatchMapping khác.
4. AuthorService và PublisherService cung cấp bulk method nhận danh sách ID.
5. Dùng Map tra cứu theo ID ở service rồi tạo kết quả đúng thứ tự Book đầu vào.
6. Xử lý sách không có tác giả hoặc nhà xuất bản theo nullability của SDL.
7. Cấu hình maxBatchSize phù hợp với giới hạn truy vấn.
8. Viết GraphQlTester kiểm tra response và Mockito verify số lần gọi bulk service.
9. So sánh số truy vấn khi dùng @SchemaMapping gọi repository từng sách với khi dùng @BatchMapping.

Sau bài thực hành, hãy giải thích vì sao DataLoader gom các yêu cầu trong cùng execution, vì sao List phải giữ thứ tự source và khi nào Map là lựa chọn an toàn hơn.

## Ghi nhớ

Nested field có thể gây N+1 khi mỗi parent object gọi một truy vấn riêng. @BatchMapping cho phép Spring for GraphQL nhận nhiều source object, gom key và tải dữ liệu theo lô thông qua DataLoader. Batch method có thể trả Map gắn source với kết quả hoặc List có thứ tự khớp chính xác với danh sách source. Hãy loại key trùng, xử lý quan hệ không tồn tại theo nullability, giới hạn batch size theo hệ thống phụ thuộc và kiểm thử cả dữ liệu lẫn số lần gọi service. Dùng DataLoader tường minh khi cần key hoặc cache tùy chỉnh; với một nested field đơn giản, @BatchMapping thường là lựa chọn trực tiếp.
