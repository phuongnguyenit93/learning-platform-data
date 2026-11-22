# DataLoader là gì trong GraphQL?

DataLoader là cơ chế gom nhiều lần tải dữ liệu riêng lẻ thành một hoặc một số lần tải theo lô, đồng thời lưu cache các kết quả trong phạm vi một lần thực thi. Nó đặc biệt hữu ích khi GraphQL phân giải field lồng nhau cho nhiều object cha và mỗi field con cần truy cập dữ liệu liên quan. Nếu mỗi resolver tự gọi repository cho từng object, ứng dụng dễ gặp vấn đề N+1; DataLoader giúp gom các key lại để service hoặc repository truy vấn theo lô.

Trong Spring for GraphQL, DataLoader được tích hợp với GraphQL Java thông qua `DataLoaderRegistry` và `BatchLoaderRegistry`. Spring tạo registry theo từng GraphQL request và cung cấp các DataLoader đã đăng ký cho resolver. Bạn cũng có thể dùng `@BatchMapping` như một cách khai báo ngắn gọn cho field cần batch loading.

Sau bài này, bạn có thể:

- Hiểu DataLoader giải quyết vấn đề N+1 như thế nào.
- Nắm cơ chế batching, cache và dispatch.
- Phân biệt batch loader trả list theo thứ tự với mapped batch loader trả map theo key.
- Đăng ký DataLoader bằng `BatchLoaderRegistry` trong Spring for GraphQL.
- Dùng DataLoader trong `@SchemaMapping` để tải dữ liệu quan hệ.
- Hiểu phạm vi cache theo request và các giới hạn của DataLoader.
- Biết khi nào nên dùng DataLoader, `@BatchMapping` hoặc truy vấn join/projection.

## 1. Bài toán N+1 trong GraphQL

Giả sử schema có sách và tác giả:

```graphql
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
```

Client yêu cầu danh sách sách cùng tên tác giả:

```graphql
query {
    books {
        id
        title
        author {
            name
        }
    }
}
```

Một cách triển khai đơn giản là resolver `Query.books` lấy toàn bộ sách, sau đó resolver `Book.author` gọi repository tìm tác giả cho từng cuốn:

```java
@QueryMapping
public List<Book> books() {
    return bookRepository.findAll();
}

@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorRepository.findById(book.authorId()).orElse(null);
}
```

Nếu có 100 cuốn sách, ứng dụng có thể thực hiện:

- 1 truy vấn lấy danh sách sách.
- 100 truy vấn lấy tác giả, mỗi truy vấn cho một cuốn sách.

Tổng cộng là 101 lần truy cập database trong trường hợp xấu nhất. Đây là vấn đề N+1: một truy vấn ban đầu lấy N object, sau đó phát sinh thêm N truy vấn để tải dữ liệu liên quan.

Số lần truy vấn thực tế còn phụ thuộc cache, quan hệ dữ liệu, cách repository hoạt động và số tác giả trùng nhau. Tuy nhiên, resolver gọi repository riêng cho từng object cha vẫn có nguy cơ tăng số lần truy cập theo số phần tử.

## 2. DataLoader giải quyết N+1 như thế nào?

DataLoader thay vì tải ngay khi resolver yêu cầu một key, nó ghi nhận key vào một hàng đợi. Khi GraphQL execution đến thời điểm dispatch, DataLoader gom các key đang chờ và gọi batch loader một lần. Batch loader nhận tập key, truy vấn dữ liệu theo lô rồi trả kết quả tương ứng.

Ví dụ, 100 cuốn sách có các `authorId` là `1`, `2`, `3`, ... Resolver gọi `load(authorId)` cho từng cuốn. DataLoader có thể gom các key thành một batch `[1, 2, 3, ...]`; service thực hiện một truy vấn dạng `WHERE id IN (...)` rồi trả về tác giả tương ứng.

```mermaid
flowchart TD
    A[Query lấy danh sách Book] --> B[GraphQL phân giải Book.author cho từng Book]
    B --> C[DataLoader.load(authorId)]
    C --> D[Đưa key vào hàng đợi]
    D --> E[Dispatch batch]
    E --> F[BatchLoader nhận nhiều authorId]
    F --> G[Service truy vấn theo lô]
    G --> H[Trả kết quả theo key]
    H --> I[GraphQL tiếp tục phân giải Author.name]
```

Nếu backend thực hiện một truy vấn hiệu quả cho cả batch, số lần truy cập có thể giảm từ 1 + N xuống còn 1 + số batch. Với 100 sách trong một batch, ví dụ trên có thể chỉ cần một truy vấn lấy sách và một truy vấn lấy tác giả.

DataLoader không tự viết câu SQL tối ưu. Nó chỉ gom yêu cầu và quản lý cache; batch loader/service phải thực hiện truy vấn nhiều key thật sự. Nếu batch loader vẫn lặp từng key rồi gọi repository một lần cho mỗi key, N+1 vẫn còn.

## 3. Hai khả năng chính: batching và caching

DataLoader thường cung cấp hai khả năng bổ sung cho nhau:

**Batching** gom nhiều yêu cầu `load(key)` phát sinh trong một khoảng thực thi thành một lần gọi batch loader. Thay vì gọi service cho từng key, ứng dụng gọi một lần với nhiều key.

**Caching** lưu kết quả theo key trong instance DataLoader. Nếu cùng một key được yêu cầu nhiều lần trong cùng phạm vi loader, DataLoader có thể dùng lại kết quả đã tải hoặc đang chờ tải, tránh truy vấn trùng lặp.

Ví dụ, nếu nhiều sách cùng có `authorId = 7`, resolver có thể gọi `load(7)` nhiều lần nhưng DataLoader mặc định cache theo key, nhờ đó không cần tải tác giả 7 lặp lại trong cùng request.

| Khả năng | Tác dụng | Điều cần nhớ |
| --- | --- | --- |
| Batching | Giảm số lần gọi service/database | Batch loader phải truy vấn nhiều key cùng lúc |
| Caching | Tránh tải lặp cùng key | Cache thuộc instance DataLoader, cần đúng phạm vi request |

Batching và caching không giống nhau. Có thể tắt cache mà vẫn batching được; cũng có thể dùng cache để tránh lặp key dù batch chỉ có một phần tử. Mục tiêu và cấu hình của hai tính năng cần được hiểu riêng.

## 4. DataLoader trong GraphQL Java

GraphQL Java sử dụng thư viện `java-dataloader`. Một `DataLoader<K, V>` nhận key kiểu `K` và trả kết quả kiểu `V` dưới dạng bất đồng bộ, thường là `CompletableFuture<V>`.

Ví dụ về cách gọi:

```java
CompletableFuture<Author> authorFuture = authorDataLoader.load(book.authorId());
```

`load` không nhất thiết truy vấn database ngay tại dòng code đó. Nó đăng ký key vào DataLoader và trả về future. Khi GraphQL dispatch loader, batch function được gọi với nhiều key. Sau khi future hoàn tất, GraphQL tiếp tục phân giải các field con của `Author`.

DataLoader thường được dùng trong resolver của field quan hệ, ví dụ `Book.author`, `Order.customer` hoặc `Product.category`. Resolver vẫn có thể trả `CompletableFuture`, `CompletionStage` hoặc kiểu reactive tương thích với Spring for GraphQL.

Không gọi `join()` hoặc `get()` trên future trong resolver để chờ kết quả đồng bộ. Làm vậy có thể chặn thread và phá vỡ lợi ích bất đồng bộ. Hãy trả future cho GraphQL engine xử lý.

## 5. BatchLoader trả về List: phải giữ đúng thứ tự

Một kiểu batch loader nhận danh sách key và trả danh sách value theo cùng thứ tự:

```java
BatchLoader<Long, Author> batchLoader = authorIds ->
        authorService.findAuthorsInOrderAsync(authorIds);
```

Ở đây `findAuthorsInOrderAsync` có thể trả về `CompletionStage<List<Author>>`; phần triển khai bên trong phải bảo đảm thứ tự như danh sách key.

Nếu key đầu vào là `[10, 20, 30]`, kết quả phải có vị trí tương ứng:

| Vị trí | Key | Value tại cùng vị trí |
| --- | --- | --- |
| 0 | 10 | Author có ID 10 |
| 1 | 20 | Author có ID 20 |
| 2 | 30 | Author có ID 30 |

Batch loader dạng list phải bảo đảm kết quả có cùng số phần tử và đúng thứ tự với danh sách key theo hợp đồng của `BatchLoader`. Nếu repository trả kết quả không theo thứ tự input, cần dựng lại thứ tự trước khi trả list.

Ví dụ:

```java
public List<Author> findAuthorsInOrder(List<Long> authorIds) {
    Iterable<Author> foundAuthors = authorRepository.findAllById(authorIds);
    Map<Long, Author> byId = StreamSupport.stream(foundAuthors.spliterator(), false)
            .collect(Collectors.toMap(Author::id, Function.identity()));

    return authorIds.stream()
            .map(byId::get)
            .toList();
}
```

Nếu một key không có bản ghi, list có thể chứa null ở đúng vị trí khi kiểu dữ liệu cho phép; nếu không muốn trả null, hãy xác định semantics lỗi hoặc kết quả vắng mặt rõ ràng.

## 6. MappedBatchLoader: trả Map theo key

Khi repository không bảo đảm thứ tự hoặc có thể không tìm thấy một số key, mapped batch loader thường dễ dùng hơn. Nó nhận tập key và trả map từ key sang value:

```java
MappedBatchLoader<Long, Author> mappedBatchLoader = authorIds ->
        authorService.findAuthorsByIdsAsync(authorIds);
```

Trong ví dụ này, `findAuthorsByIdsAsync` trả về `CompletionStage<Map<Long, Author>>`.

Ví dụ map:

```java
{
    10L -> Author(10, "An"),
    30L -> Author(30, "Binh")
}
```

Nếu key `20` không có trong map, DataLoader sẽ không có value cho key đó; resolver nhận kết quả vắng mặt theo semantics của loader, thường là null. Cách này không yêu cầu map phải giữ thứ tự như danh sách đầu vào vì mỗi kết quả được gắn trực tiếp với key.

Mapped loader phù hợp khi:

- Repository trả dữ liệu theo thứ tự riêng.
- Một số key có thể không tồn tại.
- Cần ghép kết quả bằng ID một cách rõ ràng.
- Batch query trả về map hoặc dữ liệu cần group theo key.

Ví dụ service:

```java
public Map<Long, Author> findAuthorsByIds(Set<Long> authorIds) {
    Iterable<Author> foundAuthors = authorRepository.findAllById(authorIds);
    return StreamSupport.stream(foundAuthors.spliterator(), false)
            .collect(Collectors.toMap(Author::id, Function.identity()));
}
```

Service cần xử lý trường hợp ID trùng lặp, dữ liệu không tồn tại và quyền truy cập theo hợp đồng của ứng dụng.

## 7. DataLoaderRegistry và phạm vi cache

GraphQL Java quản lý DataLoader thông qua `DataLoaderRegistry`. Registry chứa các DataLoader có tên và được gắn với một lần thực thi GraphQL. Resolver lấy loader từ registry bằng tên tương ứng hoặc thông qua cơ chế tích hợp của framework.

Phạm vi của registry rất quan trọng:

- DataLoader có cache theo instance.
- Nếu dùng chung một instance giữa nhiều request, cache có thể làm dữ liệu của request trước ảnh hưởng request sau.
- Nếu cache chứa dữ liệu phụ thuộc người dùng hoặc tenant, dùng cache toàn cục có thể gây rò rỉ dữ liệu.
- Tạo registry/loader theo request giúp giới hạn cache trong một lần thực thi và giữ đúng ngữ cảnh bảo mật.

Trong Spring for GraphQL, `BatchLoaderRegistry` được thiết kế để đăng ký batch loader và khởi tạo DataLoader tương ứng trong `DataLoaderRegistry` của từng request. Nhờ đó, controller có thể nhận DataLoader như một tham số và không cần tự quản lý registry cho mỗi request.

Không tự tạo static `DataLoader` hoặc singleton cache chứa dữ liệu người dùng. Cache request-scoped không thay thế cache ứng dụng hoặc cache database; nó chỉ tránh lặp tải trong cùng GraphQL execution.

## 8. Đăng ký DataLoader bằng BatchLoaderRegistry

Spring for GraphQL cung cấp `BatchLoaderRegistry` để đăng ký loader theo cặp key/value type. Ví dụ, tải tác giả theo ID:

```java
@Configuration
public class GraphQlBatchConfiguration {

    public GraphQlBatchConfiguration(
            BatchLoaderRegistry registry,
            AuthorService authorService) {

        registry.forTypePair(Long.class, Author.class)
                .registerMappedBatchLoader((authorIds, environment) ->
                        authorService.findAuthorsByIds(authorIds));
    }
}
```

Trong ví dụ, `findAuthorsByIds` trả về `Mono<Map<Long, Author>>` hoặc kiểu reactive phù hợp với chữ ký mapped batch loader mà phiên bản Spring for GraphQL đang dùng. Nếu service blocking, có thể dùng adapter phù hợp để cô lập I/O blocking; không thực hiện truy vấn blocking trực tiếp trên event-loop của WebFlux.

`BatchLoaderRegistry` đăng ký loader để Spring tạo DataLoader trong registry của từng request. Nó cũng hỗ trợ truyền context từ GraphQL request đến batch loader, hữu ích khi việc tải dữ liệu phụ thuộc thông tin đã xác thực hoặc tenant context. Không lấy tenant/user ID từ key do client tùy ý gửi nếu thông tin đó phải đến từ security context.

Spring Boot thường cung cấp sẵn bean `BatchLoaderRegistry`. Có thể inject bean đó vào cấu hình hoặc component cần đăng ký loader; không cần tự tạo một registry toàn cục cho tất cả request.

## 9. Dùng DataLoader trong @SchemaMapping

Sau khi đăng ký loader, resolver field `Book.author` có thể nhận `DataLoader<Long, Author>`:

```java
@Controller
public class BookController {

    @SchemaMapping(typeName = "Book", field = "author")
    public CompletableFuture<Author> author(
            Book book,
            DataLoader<Long, Author> authorDataLoader) {

        return authorDataLoader.load(book.authorId());
    }
}
```

Spring for GraphQL cung cấp DataLoader phù hợp từ request registry cho method argument. Mỗi resolver gọi `load` với ID tác giả của sách. Các key được gom và batch loader đăng ký trước đó sẽ gọi service một lần cho nhóm ID.

Client vẫn truy vấn như bình thường:

```graphql
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
```

Không cần thay đổi GraphQL schema chỉ vì thêm DataLoader. DataLoader là cơ chế triển khai ở server; hợp đồng field `Book.author` vẫn giữ nguyên.

## 10. @BatchMapping là cách khai báo batch thuận tiện

Spring for GraphQL cung cấp `@BatchMapping` để triển khai batch loading trực tiếp cho một field. Thay vì tự khai báo `BatchLoaderRegistry` và nhận DataLoader trong `@SchemaMapping`, method nhận danh sách source object và trả map kết quả theo từng source:

```java
@Controller
public class BookController {

    private final AuthorService authorService;

    public BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Mono<Map<Book, Author>> author(List<Book> books) {
        Set<Long> authorIds = books.stream()
                .map(Book::authorId)
                .collect(Collectors.toSet());

        return authorService.findAuthorsByIds(authorIds)
                .map(authorsById -> {
                    Map<Book, Author> result = new HashMap<>();
                    for (Book book : books) {
                        result.put(book, authorsById.get(book.authorId()));
                    }
                    return result;
                });
    }
}
```

Spring for GraphQL dùng `@BatchMapping` để đăng ký batch loader cho field tương ứng. Kết quả map liên kết từng source object với giá trị field cần trả về. Nếu dùng kiểu trả về `Flux<V>` thay vì map, cần tuân thủ quy tắc thứ tự tương ứng với danh sách source theo API của `@BatchMapping`.

`@BatchMapping` phù hợp khi batch logic chỉ phục vụ một field cụ thể. Dùng `BatchLoaderRegistry` trực tiếp khi muốn tái sử dụng loader theo key ở nhiều resolver hoặc cần kiểm soát rõ việc gọi `DataLoader.load(...)`.

Không đăng ký đồng thời `@SchemaMapping` và `@BatchMapping` cho cùng field coordinate nếu không có chủ đích rõ ràng; hai cách này đều cung cấp data fetcher cho field đó và có thể xung đột.

## 11. Cache key và cache behavior

DataLoader mặc định cache theo key trong instance loader. Vì vậy, kiểu key cần có `equals` và `hashCode` đúng. Với ID dạng `Long`, `String` hoặc UUID, semantics thường rõ ràng. Nếu dùng object làm key, cần bảo đảm equality ổn định và không phụ thuộc mutable field.

Một số tình huống cần cân nhắc:

- Cùng một key được load nhiều lần trong request: cache có thể dùng chung kết quả.
- Cùng một key nhưng kết quả phụ thuộc locale, tenant hoặc quyền: đưa thông tin đó vào key hoặc thiết kế loader/cache scope phù hợp; không được dùng chung kết quả sai ngữ cảnh.
- Dữ liệu thay đổi giữa các mutation trong cùng request: cache có thể giữ giá trị cũ; cân nhắc clear/prime key sau khi mutation cập nhật dữ liệu.
- Không muốn cache trong loader: có thể cấu hình DataLoader không cache hoặc dùng cache map phù hợp, nhưng batching vẫn có thể hoạt động.

DataLoader cache thường chỉ tồn tại trong một request, nên không phải nơi lưu cache dài hạn. Nếu cần cache giữa nhiều request, dùng cache ứng dụng có TTL, invalidation và phân vùng quyền truy cập rõ ràng.

## 12. Dispatch và bất đồng bộ

DataLoader gom các lệnh `load` trước khi batch function được gọi. GraphQL Java điều phối dispatch trong quá trình thực thi để chờ và giải quyết các future. Khi tích hợp qua Spring for GraphQL, thông thường resolver chỉ cần gọi `load` và trả future; không tự gọi `dispatch()` trong từng resolver.

Ví dụ không nên làm:

```java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book, DataLoader<Long, Author> loader) {
    return loader.load(book.authorId()).join();
}
```

`join()` chặn thread để đợi kết quả. Điều này làm mất lợi ích bất đồng bộ và có thể gây nghẽn khi có nhiều field đang chờ batch.

Nên trả future:

```java
@SchemaMapping(typeName = "Book", field = "author")
public CompletableFuture<Author> author(
        Book book,
        DataLoader<Long, Author> loader) {
    return loader.load(book.authorId());
}
```

Nếu service trả `Mono`, Spring for GraphQL hỗ trợ kiểu reactive ở các boundary phù hợp. Hãy giữ pipeline non-blocking trong WebFlux và không gọi `.block()` trong resolver.

## 13. DataLoader không thay thế mọi kỹ thuật tối ưu

DataLoader rất hữu ích cho quan hệ được tải từ resolver lồng nhau, nhưng không phải lúc nào cũng là lựa chọn tốt nhất.

| Tình huống | Giải pháp nên cân nhắc |
| --- | --- |
| Danh sách sách cùng cần tác giả theo ID | DataLoader hoặc `@BatchMapping` |
| Một truy vấn có thể join tác giả hiệu quả và luôn cần tác giả | Join fetch hoặc projection trong repository |
| Client chỉ chọn `Book.id` và `Book.title` | Projection chỉ lấy field cần thiết |
| Field được tải từ REST service hỗ trợ bulk endpoint | DataLoader gọi bulk endpoint |
| Một field là phép tính thuần từ object hiện có | Resolver trực tiếp, không cần DataLoader |
| Dữ liệu dùng chung qua nhiều request | Cache ứng dụng riêng, không dùng request DataLoader cache |

Nếu một query database duy nhất có thể trả toàn bộ dữ liệu với join/projection hiệu quả, việc thêm DataLoader có thể làm hệ thống phức tạp mà không cải thiện hiệu năng. Ngược lại, nếu resolver cần tải dữ liệu từ nhiều nguồn hoặc chỉ một số field được client chọn, DataLoader có thể giúp gom các lần gọi một cách linh hoạt.

## 14. Giới hạn và lưu ý khi dùng DataLoader

- **Batch size:** một batch quá lớn có thể vượt giới hạn bind parameter hoặc làm query nặng. Có thể cấu hình giới hạn batch size và để loader chia thành nhiều batch.
- **Key trùng lặp:** cache mặc định có thể loại bỏ yêu cầu trùng key; nếu cần xử lý từng vị trí input, phải hiểu cách loader phân phối cùng một value về các lần load.
- **Thiếu dữ liệu:** quyết định key không tồn tại sẽ trả null, lỗi hay một kiểu kết quả riêng.
- **Thứ tự:** list batch loader phải giữ thứ tự key; mapped loader ánh xạ bằng key.
- **Request context:** batch loader cần nhận đúng security/tenant context; không dùng singleton loader giữ state của người dùng.
- **Lỗi batch:** nếu batch function thất bại toàn bộ, nhiều field phụ thuộc batch có thể cùng nhận lỗi; nếu cần lỗi riêng từng key, hãy dùng cơ chế per-key error phù hợp của DataLoader.
- **Mutation và cache:** nếu dữ liệu bị thay đổi trong cùng request, cần xem xét clear hoặc prime cache để các field sau không dùng giá trị cũ.
- **Batching không đảm bảo query nhanh:** đo SQL, network call, batch size và latency để xác nhận hiệu quả.

## 15. Kiểm thử DataLoader

Nên kiểm tra cả kết quả và số lần batch service được gọi. Ví dụ với resolver dùng DataLoader, test có thể xác nhận nhiều sách được trả cùng tác giả đúng và batch service chỉ nhận một nhóm ID trong một lần dispatch.

Các tình huống nên kiểm thử:

1. Nhiều source object gọi `load` và được gom thành batch.
2. Hai source dùng cùng key không tạo truy vấn trùng khi cache bật.
3. Batch loader trả kết quả đúng key hoặc đúng thứ tự theo loại loader.
4. Key không tồn tại có kết quả đúng semantics.
5. Lỗi batch được chuyển thành GraphQL error phù hợp.
6. Hai request khác nhau không chia sẻ cache của DataLoader.
7. Security/tenant context được truyền đúng đến batch loader.
8. Mutation thay đổi dữ liệu không để cache trong cùng request trả giá trị lỗi thời.
9. `@BatchMapping` hoạt động với toàn bộ source list và trả mapping chính xác.

Ví dụ kiểm thử từ GraphQL client:

```java
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
```

Để xác nhận batching thực sự, dùng spy/mock service hoặc integration test quan sát số lần repository được gọi. Chỉ kiểm tra response đúng không đủ để chứng minh N+1 đã được loại bỏ.

## 16. Những lỗi thường gặp

- **Chỉ dùng `DataLoader.load` nhưng batch loader truy vấn từng key:** N+1 vẫn tồn tại; service phải có bulk query.
- **Trả list sai thứ tự:** value bị gán nhầm key; mapped loader hoặc dựng lại thứ tự trước khi trả.
- **Dùng DataLoader singleton toàn ứng dụng:** cache có thể rò rỉ giữa request và người dùng.
- **Gọi `join()` hoặc `get()` trong resolver:** chặn thread và phá vỡ execution bất đồng bộ.
- **Tự dispatch trong mỗi resolver:** có thể phá cơ chế gom key của GraphQL execution; để engine điều phối khi dùng Spring integration.
- **Nhầm DataLoader cache với cache dài hạn:** cache loader thường chỉ có phạm vi request.
- **Bỏ qua authorization trong batch loader:** một batch có thể chứa nhiều ID; phải bảo vệ từng resource theo caller/tenant.
- **Dùng DataLoader cho phép tính đơn giản:** thêm phức tạp mà không có lợi ích tải dữ liệu.
- **Không cập nhật cache sau mutation:** field đọc sau mutation trong cùng request có thể nhận dữ liệu cũ.
- **Chỉ kiểm tra output mà không đo batch invocation:** không xác nhận được số lần truy cập backend đã giảm.

## 17. Quy trình triển khai DataLoader trong Spring for GraphQL

Khi một field quan hệ có nguy cơ N+1, hãy thực hiện:

1. Đo số lần resolver/repository được gọi với một query đại diện.
2. Xác định key cần dùng để tải dữ liệu liên quan, ví dụ `authorId`.
3. Tạo service/repository method có khả năng tải nhiều key trong một lần.
4. Chọn list batch loader nếu có thể bảo đảm thứ tự, hoặc mapped batch loader nếu kết quả cần ánh xạ theo key.
5. Đăng ký loader qua `BatchLoaderRegistry` để Spring tạo DataLoader theo request.
6. Nhận DataLoader trong `@SchemaMapping` và trả future từ `load(key)`.
7. Hoặc dùng `@BatchMapping` nếu logic batch chỉ phục vụ một field.
8. Bảo đảm cache không vượt phạm vi request và context bảo mật được truyền đúng.
9. Kiểm thử dữ liệu, thứ tự, key thiếu, lỗi và số lần gọi backend.
10. So sánh hiệu năng trước/sau; cân nhắc join hoặc projection nếu phù hợp hơn.

DataLoader là cơ chế phối hợp giữa GraphQL execution và batch loading ở server. Nó gom nhiều yêu cầu tải dữ liệu, cache kết quả theo key trong phạm vi loader và cho phép resolver tiếp tục bất đồng bộ. Trong Spring for GraphQL, `BatchLoaderRegistry` giúp đăng ký loader theo request, còn `@BatchMapping` cung cấp cách khai báo batch field ngắn gọn. Khi batch loader thực sự truy vấn theo lô, giữ đúng mapping key/value và được kiểm thử về số lần truy cập backend, DataLoader giúp giải quyết N+1 mà vẫn giữ schema GraphQL linh hoạt.

## Tài liệu tham khảo

- [Spring for GraphQL — Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html#execution.batching)
- [Spring for GraphQL — Annotated Controllers and @BatchMapping](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.batch-mapping)
- [GraphQL Java — DataLoader](https://www.graphql-java.com/documentation/batching/)
- [java-dataloader — DataLoader concepts and API](https://github.com/graphql-java/java-dataloader)
- [Spring for GraphQL — BatchLoaderRegistry API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/execution/BatchLoaderRegistry.html)
