# Batch loader trả về Mono

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích cách Spring for GraphQL đăng ký batch loading function bằng `BatchLoaderRegistry`.
- Phân biệt `registerMappedBatchLoader` trả về `Mono<Map<K,V>>` với `registerBatchLoader` trả về `Flux<V>`.
- Thiết kế hợp đồng giữa tập key đầu vào và map kết quả.
- Dùng `DataLoader.load()` trong `@SchemaMapping` để trì hoãn và gom các lần tải dữ liệu.
- Hiểu cách Spring tạo DataLoader theo từng GraphQL request và chia sẻ GraphQLContext với batch loader.
- Xử lý key không tìm thấy, publisher rỗng, lỗi và giới hạn kích thước batch.
- Phân biệt BatchLoaderRegistry với `@BatchMapping`.
- Kiểm thử batch loading để xác nhận dữ liệu đúng và số lần truy cập nguồn dữ liệu được giảm.

## 1. Vì sao batch loader có thể trả về Mono?

Khi một GraphQL query lấy danh sách object rồi truy vấn field liên quan của từng object, server dễ gặp vấn đề N+1.

Ví dụ, client lấy 20 quyển sách và tên tác giả:

~~~graphql
query {
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

Nếu resolver của `Book.author` gọi database riêng cho mỗi quyển sách, server có thể thực hiện:

- Một truy vấn lấy danh sách 20 Book.
- Hai mươi truy vấn riêng để lấy Author tương ứng.

Tổng cộng là 21 lần truy cập dữ liệu trong trường hợp đơn giản. Khi danh sách lớn hơn hoặc có nhiều quan hệ lồng nhau, số lần gọi có thể tăng nhanh.

DataLoader giải quyết vấn đề này bằng cách trì hoãn từng yêu cầu tải dữ liệu, gom các key lại và gọi batch loader một lần cho một nhóm key. Batch loader có thể truy vấn nhiều bản ghi trong cùng một lần gọi và trả kết quả dưới dạng publisher.

Trong Spring for GraphQL, `BatchLoaderRegistry` hỗ trợ đăng ký mapped batch loader có chữ ký:

~~~java
BiFunction<
        Set<K>,
        BatchLoaderEnvironment,
        Mono<Map<K, V>>
>
~~~

Nghĩa là:

- Đầu vào là tập key cần tải.
- Tham số môi trường cung cấp context của batch.
- Kết quả là một `Mono` phát ra map từ key sang value.

`Mono<Map<K,V>>` phù hợp khi số key đầu vào có thể khác số value tìm thấy. Map liên kết từng kết quả bằng key nên không phụ thuộc vào thứ tự trả về của database.

## 2. Phân biệt BatchLoader và MappedBatchLoader

Spring for GraphQL cung cấp hai cách đăng ký batch function thường gặp:

| API | Đầu vào | Kiểu trả về | Quy tắc kết quả |
|---|---|---|---|
| `registerBatchLoader` | `List<K>` | `Flux<V>` | Số lượng và thứ tự value phải khớp với danh sách key |
| `registerMappedBatchLoader` | `Set<K>` | `Mono<Map<K,V>>` | Map liên kết value với key, không phụ thuộc thứ tự |

### Batch loader theo thứ tự

Với `registerBatchLoader`, batch function nhận một danh sách key và trả về các value theo đúng thứ tự tương ứng.

Ví dụ key là:

~~~text
[101, 102, 103]
~~~

Kết quả phải có thứ tự:

~~~text
[Author(101), Author(102), Author(103)]
~~~

Nếu không tìm thấy key 102, batch function phải giữ đúng vị trí bằng một giá trị null theo hợp đồng của `BatchLoader`. Cách này có thể khó xử lý nếu nguồn dữ liệu trả kết quả theo thứ tự khác hoặc không có đủ bản ghi.

### Mapped batch loader

Với `registerMappedBatchLoader`, đầu vào là tập key và kết quả là map:

~~~text
Keys: {101, 102, 103}

Map:
  101 -> Author(101)
  103 -> Author(103)
~~~

Key 102 không xuất hiện trong map vì không tìm thấy Author tương ứng. DataLoader có thể trả null cho lần tải key đó.

Đây là lựa chọn thuận tiện khi truy vấn database bằng câu lệnh `WHERE id IN (...)`, vì database không cam kết trả bản ghi theo đúng thứ tự của danh sách key đầu vào.

Bài học này tập trung vào `registerMappedBatchLoader` và kết quả `Mono<Map<K,V>>`.

## 3. Khai báo schema và model ví dụ

Giả sử ứng dụng quản lý Book và Author. Một Book lưu `authorId`; thông tin Author được tải từ một nguồn dữ liệu riêng.

SDL:

~~~graphql
type Query {
  books: [Book!]!
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

Java model có thể dùng record:

~~~java
public record Book(
        Long id,
        String title,
        Long authorId) {
}

public record Author(
        Long id,
        String name) {
}
~~~

Service tải nhiều tác giả theo tập ID:

~~~java
public interface AuthorService {
    Flux<Author> findAllByIds(Collection<Long> authorIds);
}
~~~

Service lấy danh sách sách dùng trong Query:

~~~java
public interface BookService {
    Flux<Book> findAll();
}
~~~

Service trả về `Flux<Author>` vì một lần truy vấn có thể tìm thấy nhiều bản ghi. Batch loader sẽ gom Flux thành một map bằng `collectMap`, tạo ra `Mono<Map<Long, Author>>`.

## 4. Đăng ký BatchLoaderRegistry

Spring Boot GraphQL starter cung cấp bean `BatchLoaderRegistry`. Có thể inject registry vào một component hoặc lớp cấu hình để đăng ký batch loading function.

Ví dụ:

~~~java
@Component
public class AuthorBatchLoader {

    public AuthorBatchLoader(
            BatchLoaderRegistry registry,
            AuthorService authorService) {

        registry.forTypePair(Long.class, Author.class)
                .registerMappedBatchLoader((authorIds, environment) ->
                        authorService.findAllByIds(authorIds)
                                .collectMap(Author::id)
                );
    }
}
~~~

Giải thích:

- `forTypePair(Long.class, Author.class)` khai báo kiểu key là Long và kiểu value là Author.
- `registerMappedBatchLoader(...)` đăng ký function nhận tập ID và trả `Mono<Map<Long, Author>>`.
- `authorIds` là tập key được DataLoader gom lại trong một lần dispatch.
- `authorService.findAllByIds(authorIds)` truy vấn các tác giả cần thiết.
- `collectMap(Author::id)` thu thập các Author thành map, trong đó ID là key.

Vì `collectMap` phát ra một map khi Flux hoàn tất, kết quả của batch loader là một `Mono<Map<Long, Author>>`. Nếu không tìm thấy bản ghi nào, `collectMap` vẫn phát ra map rỗng.

### Vì sao dùng forTypePair?

`forTypePair` khai báo cả kiểu key và value. Spring dùng kiểu value để đặt tên DataLoader mặc định. Với ví dụ trên, tên mặc định dựa trên tên class đầy đủ của `Author`.

Nhờ vậy, controller có thể khai báo tham số `DataLoader<Long, Author>` mà thường không cần truyền tên DataLoader thủ công.

Nếu cần đăng ký nhiều loader cùng trả về một kiểu value nhưng có mục đích khác nhau, có thể đặt tên riêng bằng `forName(...)` và `withName(...)`. Khi dùng tên tùy chỉnh, cần bảo đảm cách controller lấy DataLoader trùng với tên đã đăng ký.

## 5. Dùng DataLoader trong @SchemaMapping

Sau khi đăng ký batch function, resolver của field liên quan không gọi service trực tiếp. Nó yêu cầu DataLoader tải value theo key.

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Flux<Book> books() {
        return bookService.findAll();
    }

    @SchemaMapping
    public CompletableFuture<Author> author(
            Book book,
            DataLoader<Long, Author> authorLoader) {

        return authorLoader.load(book.authorId());
    }
}
~~~

Trong ví dụ:

- `Book book` là source object của field `Book.author`.
- `book.authorId()` là key cần tải.
- `authorLoader.load(...)` đưa key vào hàng đợi của DataLoader.
- `load()` trả về `CompletableFuture<Author>`, được GraphQL chờ trong quá trình thực thi.

Nếu client yêu cầu author của nhiều Book, các lần gọi `load` được xếp hàng. DataLoader có thể gom những key đó và gọi batch function đã đăng ký.

Không nên gọi `authorService.findById(book.authorId())` trực tiếp trong resolver này, vì như vậy mỗi Book lại tạo một truy vấn riêng và không tận dụng batch loading.

### Trường hợp authorId có thể null

Nếu một Book không có tác giả, có thể bỏ qua DataLoader:

~~~java
@SchemaMapping
public CompletableFuture<Author> author(
        Book book,
        DataLoader<Long, Author> authorLoader) {

    if (book.authorId() == null) {
        return CompletableFuture.completedFuture(null);
    }

    return authorLoader.load(book.authorId());
}
~~~

SDL đang khai báo `author: Author` là nullable nên giá trị null có thể được trả về. Nếu schema khai báo `author: Author!`, ứng dụng phải bảo đảm có tác giả hoặc trả lỗi phù hợp.

## 6. Luồng thực thi từ load đến Mono<Map>

Khi GraphQL thực thi query có nhiều Book, quá trình có thể diễn ra như sau:

~~~mermaid
sequenceDiagram
    participant G as GraphQL Engine
    participant C as Book.author Resolver
    participant D as DataLoader
    participant B as BatchLoaderRegistry
    participant S as AuthorService

    G->>C: Resolve Book 1.author
    C->>D: load(101)
    D-->>C: CompletableFuture pending

    G->>C: Resolve Book 2.author
    C->>D: load(102)
    D-->>C: CompletableFuture pending

    G->>C: Resolve Book 3.author
    C->>D: load(103)
    D-->>C: CompletableFuture pending

    D->>B: Dispatch {101, 102, 103}
    B->>S: findAllByIds(keys)
    S-->>B: Flux<Author>
    B->>B: collectMap(Author::id)
    B-->>D: Mono<Map<Long, Author>>
    D-->>C: Complete pending futures
    C-->>G: Author values
~~~

Các bước chính:

1. Mỗi resolver gọi `load(key)`.
2. DataLoader ghi nhận key và trả về future chưa hoàn tất.
3. GraphQL Java điều phối thời điểm dispatch batch loader.
4. Spring gọi function đã đăng ký trong `BatchLoaderRegistry`.
5. Service truy vấn dữ liệu theo tập key.
6. `collectMap` tạo map và phát kết quả qua Mono.
7. DataLoader ghép value theo key và hoàn tất các future đã chờ.
8. GraphQL tiếp tục serialize các field Author.

DataLoader không nhất thiết gom toàn bộ key của một query thành đúng một lần gọi. Việc dispatch phụ thuộc vào các đợt thực thi field, cấu trúc query và giới hạn batch size. Một query lớn có thể tạo nhiều batch.

## 7. Hợp đồng của Mono<Map<K,V>>

Đây là phần quan trọng nhất khi triển khai mapped batch loader.

### Key của map phải khớp key đầu vào

Nếu batch loader nhận các key:

~~~text
{101, 102, 103}
~~~

thì map phải sử dụng chính các key đó để liên kết value:

~~~java
Map<Long, Author> result = new HashMap<>();
result.put(101L, author101);
result.put(102L, author102);
result.put(103L, author103);
~~~

Không dùng index 0, 1, 2 thay cho ID nếu controller đang gọi `load(authorId)`. DataLoader cần tra map bằng chính key được gửi vào.

### Không phụ thuộc thứ tự

Database có thể trả Author theo thứ tự 103, 101, 102. Điều đó không ảnh hưởng nếu batch loader dùng `collectMap(Author::id)`.

Map giữ quan hệ:

- Key 101 nhận Author có ID 101.
- Key 102 nhận Author có ID 102.
- Key 103 nhận Author có ID 103.

Đây là lợi thế lớn so với `registerBatchLoader` dạng list phải giữ thứ tự kết quả tương ứng.

### Có thể thiếu một số key

Nếu key 102 không có bản ghi tương ứng, map có thể không chứa key đó:

~~~java
Map<Long, Author> result = Map.of(
        101L, author101,
        103L, author103
);
~~~

DataLoader trả null cho key không có value. Vì vậy, schema field cần có nullability phù hợp hoặc batch loader phải chuyển trường hợp thiếu dữ liệu thành lỗi nghiệp vụ.

### Không trả Mono rỗng để biểu diễn map không có dữ liệu

Batch function có hợp đồng trả về một map. Nếu không tìm thấy bản ghi nào, hãy phát ra map rỗng:

~~~java
return Mono.just(Collections.emptyMap());
~~~

Trong trường hợp dùng `Flux<Author>`, `collectMap(Author::id)` tự phát ra map rỗng khi Flux không có phần tử.

`Mono.empty()` có nghĩa publisher không phát ra map. Nó khác với `Mono.just(Collections.emptyMap())`. Hãy bảo đảm batch function hoàn tất bằng một map hợp lệ ngay cả khi không có kết quả.

## 8. Phân biệt lỗi và key không tìm thấy

Hai trường hợp này không giống nhau:

- **Không tìm thấy một key:** batch function vẫn thành công và map không chứa key đó.
- **Lỗi khi truy vấn nguồn dữ liệu:** publisher phát tín hiệu error và batch load thất bại.

Ví dụ, nếu database không có Author 102, map có thể chứa Author 101 và 103. DataLoader trả null cho key 102, còn hai key còn lại vẫn có kết quả.

Nếu database bị mất kết nối, không nên trả map rỗng để che giấu lỗi. Hãy để publisher phát lỗi hoặc chuyển đổi lỗi sang exception phù hợp:

Nếu muốn bổ sung xử lý lỗi cho ví dụ đăng ký ở phần trước, hãy cập nhật chính batch function đó như sau; không đăng ký thêm một loader thứ hai cùng tên:

~~~java
registry.forTypePair(Long.class, Author.class)
        .registerMappedBatchLoader((authorIds, environment) ->
                authorService.findAllByIds(authorIds)
                        .collectMap(Author::id)
                        .onErrorMap(
                                DataAccessException.class,
                                ex -> new AuthorBatchLoadException(
                                        "Unable to load authors", ex)
                        )
        );
~~~

Lỗi batch có thể ảnh hưởng đến các key thuộc batch đó. Spring for GraphQL kết hợp với cơ chế xử lý lỗi GraphQL để đưa lỗi thực thi vào response. Không nên chuyển lỗi hạ tầng thành map rỗng nếu client cần biết dữ liệu không thể tải.

## 9. BatchLoaderEnvironment và GraphQLContext

Batch loader có thể cần thêm thông tin ngoài key, ví dụ tenant, người dùng hiện tại hoặc chính sách lọc dữ liệu.

Tham số thứ hai của mapped batch loader là `BatchLoaderEnvironment`. Spring for GraphQL hỗ trợ truy cập cùng GraphQLContext của request thông qua môi trường này.

Ví dụ:

~~~java
registry.forTypePair(Long.class, Author.class)
        .registerMappedBatchLoader((authorIds, environment) -> {
            GraphQLContext graphQLContext = environment.getContext();
            String tenantId = graphQLContext.get("tenantId");

            return authorService.findAllByIdsAndTenant(
                    authorIds, tenantId)
                    .collectMap(Author::id);
        });
~~~

Trong ví dụ:

- `tenantId` được lấy từ GraphQLContext.
- Service chỉ tải tác giả thuộc tenant hiện tại.
- Kết quả map vẫn được tạo theo ID Author.

Context phải được đưa vào GraphQL request bởi tầng xác thực hoặc interceptor đáng tin cậy. Không lấy tenant hoặc user ID từ dữ liệu tùy ý của client rồi dùng làm ranh giới bảo mật.

Spring for GraphQL hỗ trợ truyền GraphQLContext tới batch loading function. Đây là một lý do nên dùng `BatchLoaderRegistry` thay vì tự tạo và đăng ký DataLoader hoàn toàn thủ công.

## 10. DataLoader được tạo theo từng request

`BatchLoaderRegistry` là registry dùng chung để khai báo batch function. Các DataLoader thực tế được đăng ký vào `DataLoaderRegistry` riêng của từng GraphQL request.

Điều này có hai ý nghĩa:

1. Các lần load trong cùng request có thể được gom và dùng chung cache.
2. Cache của request này không tự động được chia sẻ sang request khác.

Ví dụ, cùng một query có thể yêu cầu Author ID 101 ở nhiều nhánh. DataLoader mặc định có thể dùng lại kết quả đã được yêu cầu cho key 101 trong cùng request, giảm việc tải trùng.

Không nên tạo một DataLoader mutable singleton rồi dùng chung cho mọi GraphQL request. Làm vậy có thể khiến key, future hoặc dữ liệu cache của người dùng này xuất hiện trong request khác.

Spring Boot starter tự cấu hình `BatchLoaderRegistry` và kết nối registry với `DefaultExecutionGraphQlService`, nơi DataLoader được đăng ký theo từng request. Ứng dụng chỉ cần inject registry và đăng ký các batch function.

## 11. Đặt tên DataLoader khi có nhiều loader cùng value type

Với `forTypePair(keyType, valueType)`, tên mặc định của DataLoader dựa trên tên class đầy đủ của value type. Vì vậy, một tham số `DataLoader<Long, Author>` thường được Spring tìm thấy dựa trên kiểu generic.

Nếu có nhiều batch function cùng trả về Author, nhưng mỗi function có mục đích khác nhau, hãy đặt tên riêng:

~~~java
registry.<Long, Author>forName("authorById")
        .registerMappedBatchLoader((authorIds, environment) ->
                authorService.findAllByIds(authorIds)
                        .collectMap(Author::id)
        );
~~~

Controller có thể nhận DataLoader theo tên đã đăng ký:

~~~java
@SchemaMapping
public CompletableFuture<Author> author(
        Book book,
        DataLoader<Long, Author> authorById) {

    return authorById.load(book.authorId());
}
~~~

Khi dùng `forName`, tên tham số DataLoader trong handler method được dùng làm tên tra cứu. Hãy bảo đảm tên tham số được giữ trong bytecode hoặc khai báo theo quy ước tên tham số mà Spring có thể phát hiện. Nếu chỉ có một loader cho kiểu Author, `forTypePair` thường đơn giản hơn.

## 12. Tùy chỉnh DataLoaderOptions và giới hạn batch

Một batch có quá nhiều key có thể tạo truy vấn lớn, vượt giới hạn parameter của database hoặc tiêu thụ quá nhiều bộ nhớ.

DataLoader hỗ trợ cấu hình `DataLoaderOptions`, trong đó có giới hạn số key tối đa của một batch. Spring cung cấp `withOptions(...)` trên registration spec để tùy chỉnh các option.

Về nguyên tắc, có thể cấu hình:

- Batch size tối đa.
- Bật hoặc tắt cache key trong phạm vi request.
- Cache map hoặc cache key function trong trường hợp cần thiết.
- Các thống kê phục vụ quan sát hoạt động của DataLoader.

Không nên tăng batch size vô hạn. Hãy chọn giới hạn phù hợp với database, số lượng bind parameter, kích thước response và độ trễ của service phía sau.

Nếu batch size tối đa là 100 nhưng query có 350 key, DataLoader có thể chia thành nhiều batch. Do đó, batch loader phải xử lý đúng mọi tập key mà nó nhận được, không giả định số lượng key cố định.

## 13. Khi nào dùng BatchLoaderRegistry, khi nào dùng @BatchMapping?

Spring for GraphQL có `@BatchMapping`, một cách khai báo ngắn gọn cho trường hợp tải dữ liệu liên quan từ danh sách source object.

Ví dụ:

~~~java
@Controller
public class BookController {

    private final AuthorService authorService;

    public BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping
    public Mono<Map<Book, Author>> author(List<Book> books) {
        List<Long> authorIds = books.stream()
                .map(Book::authorId)
                .filter(Objects::nonNull)
                .distinct()
                .toList();

        return authorService.findAllByIds(authorIds)
                .collectMap(Author::id)
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
}
~~~

`@BatchMapping` tự đăng ký batch loading function và DataFetcher cho field tương ứng. Đây là shortcut tiện lợi khi key chính là parent object.

Với cách trả về `Map<Book, Author>`, `Book` cần có `equals` và `hashCode` ổn định để làm key. Ví dụ trên cũng giả định controller đã inject `AuthorService` qua constructor.

So sánh:

| Tiêu chí | BatchLoaderRegistry | @BatchMapping |
|---|---|---|
| Key | Có thể là ID hoặc kiểu key tùy chọn | Source/parent object |
| Đầu vào | Set key hoặc List key | List source object |
| Kết quả | Mono<Map<K,V>> hoặc Flux<V> | Mono<Map<Source,V>> hoặc Flux<V> |
| Resolver gọi load | Có, qua DataLoader | Không cần viết resolver ủy quyền riêng |
| Phù hợp | Cần tái sử dụng loader, key riêng, argument hoặc context phức tạp | Quan hệ parent-child đơn giản |
| Tùy chỉnh | Linh hoạt với DataLoaderOptions và tên loader | Ít boilerplate hơn |

Nên dùng `@BatchMapping` nếu chỉ cần tải Author cho một danh sách Book và không cần logic bổ sung tại từng field call.

Nên dùng `BatchLoaderRegistry` khi:

- Resolver cần gọi `DataLoader.load(authorId)`.
- Key không phải toàn bộ parent object.
- Nhiều field hoặc nhiều controller cần dùng cùng batch function.
- Cần kết hợp key với argument hoặc context.
- Cần đặt tên DataLoader hoặc tùy chỉnh DataLoaderOptions.

Cả hai cơ chế đều dựa trên DataLoader và BatchLoaderRegistry trong Spring for GraphQL.

## 14. Kiểm thử mapped batch loader

Kiểm thử cần xác nhận cả response lẫn việc các key được gom lại.

Ví dụ query:

~~~graphql
query {
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

Dùng `GraphQlTester` để kiểm tra kết quả:

~~~java
@Test
void shouldLoadAuthorsForBooksInBatch() {
    graphQlTester.document("""
            query {
                books {
                    id
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
}
~~~

Ngoài việc kiểm tra response, nên xác minh service batch chỉ được gọi với tập ID cần thiết:

~~~java
verify(authorService).findAllByIds(argThat(ids ->
        ids.size() == 2 &&
        ids.containsAll(Set.of(101L, 102L))));
~~~

Các tình huống nên kiểm thử:

1. Nhiều Book có các authorId khác nhau và được tải trong cùng batch.
2. Nhiều Book dùng cùng một authorId trong cùng request.
3. Một key không tồn tại và map không chứa key đó.
4. Không có bản ghi nào và batch loader trả map rỗng.
5. Service phát lỗi và GraphQL response chứa error phù hợp.
6. Tenant hoặc user context được áp dụng trong batch query.
7. Batch size giới hạn khiến một query lớn được chia thành nhiều batch.
8. Hai GraphQL request độc lập không chia sẻ cache DataLoader.
9. Field nullable xử lý đúng khi key không tìm thấy.
10. Field non-null phản ánh đúng lỗi khi value bị thiếu.

Không chỉ kiểm tra số lần gọi service. Cũng cần xác minh mỗi key nhận đúng value để phát hiện trường hợp map sai key hoặc kết quả bị gắn nhầm entity.

## 15. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| DataLoader không được tìm thấy | Key đăng ký và tên/kiểu DataLoader không khớp | Kiểm tra forTypePair, forName và generic type |
| Field author luôn null | Map không chứa key cần tải hoặc authorId sai | Kiểm tra key đầu vào và key của map |
| Kết quả gắn nhầm Author | Dùng index hoặc key không đúng | Dùng Author ID làm key của Map |
| Batch function trả lỗi khi không có dữ liệu | Trả Mono.empty thay vì map rỗng | Dùng collectMap hoặc Mono.just(emptyMap) |
| Vẫn có N+1 | Resolver gọi service trực tiếp thay vì DataLoader | Dùng loader.load(key) |
| Một batch quá lớn | Không giới hạn số key | Cấu hình max batch size |
| Cache lẫn dữ liệu giữa request | Tự chia sẻ DataLoader mutable | Để Spring đăng ký loader theo request |
| Field non-null phát sinh lỗi | Key thiếu value nhưng SDL yêu cầu non-null | Xem lại nullability hoặc xử lý thiếu dữ liệu |
| Context tenant không có trong batch | Context chưa được đưa vào GraphQL request | Kiểm tra interceptor và GraphQLContext |

## 16. Nguyên tắc thiết kế batch loader trả về Mono

Khi viết mapped batch loader:

- Dùng `forTypePair` để khai báo rõ kiểu key và value.
- Dùng `registerMappedBatchLoader` khi muốn trả `Mono<Map<K,V>>`.
- Trả map được đánh chỉ mục bằng chính key đã nhận.
- Không phụ thuộc thứ tự bản ghi từ database.
- Cho phép map thiếu key khi bản ghi liên quan không tồn tại.
- Trả map rỗng thay vì publisher rỗng khi không có kết quả.
- Phân biệt lỗi nguồn dữ liệu với trường hợp key không tìm thấy.
- Giữ DataLoader theo phạm vi GraphQL request.
- Dùng GraphQLContext cho thông tin request đáng tin cậy.
- Đặt giới hạn batch size theo khả năng nguồn dữ liệu.
- Kiểm thử cả response, key-value mapping, lỗi và số lần truy cập dữ liệu.
- Dùng `@BatchMapping` cho quan hệ parent-child đơn giản; dùng registry trực tiếp khi cần kiểm soát key và DataLoader.

## Kết luận

Mapped batch loader trả về `Mono<Map<K,V>>` là cách Spring for GraphQL kết hợp mô hình reactive với DataLoader. Batch function nhận một tập key, tải nhiều bản ghi bằng một hoặc một số truy vấn phù hợp, rồi trả về map liên kết từng key với value.

`BatchLoaderRegistry` giúp đăng ký loader tập trung và tạo DataLoader theo từng GraphQL request. Resolver gọi `DataLoader.load(key)` để đưa yêu cầu vào hàng đợi; GraphQL Java điều phối dispatch và Spring chuyển kết quả Mono thành kết quả cho các field đang chờ. Khi map được tạo đúng key, xử lý rõ key bị thiếu và giữ cache theo request, ứng dụng có thể giảm đáng kể số lần truy cập dữ liệu mà vẫn giữ được reactive flow.

## Tài liệu tham khảo

- [Spring for GraphQL — Request Execution, Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html#execution.batching)
- [Spring for GraphQL — BatchLoaderRegistry API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/execution/BatchLoaderRegistry.html)
- [Spring for GraphQL — Annotated Controllers, DataLoader and @BatchMapping](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [GraphQL Java — Batching and DataLoader](https://www.graphql-java.com/documentation/batching/)
- [GraphQL Java — java-dataloader BatchLoaderEnvironment](https://javadoc.io/doc/com.graphql-java/java-dataloader/latest/org/dataloader/BatchLoaderEnvironment.html)
