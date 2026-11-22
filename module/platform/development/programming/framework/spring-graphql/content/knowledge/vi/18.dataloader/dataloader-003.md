# BatchLoaderRegistry

Trong Spring for GraphQL, **BatchLoaderRegistry** là điểm đăng ký các batch loader để DataLoader có thể gom nhiều lần tải dữ liệu thành một lần truy vấn theo lô. Thành phần này đặc biệt hữu ích khi một GraphQL operation trả về danh sách object và mỗi object cần tải thêm dữ liệu liên quan, chẳng hạn nhiều Book cùng cần Author.

Spring quản lý việc đăng ký loader và tích hợp DataLoader vào từng GraphQL request. Controller có thể nhận một DataLoader đã được cấu hình theo kiểu key/value, gọi `load()` trong resolver và trả về future để GraphQL tiếp tục thực thi. Bài học trình bày cách đăng ký loader, cách viết batch function, phạm vi cache, tích hợp context, phân biệt với `@BatchMapping` và cách kiểm thử.

## 1. BatchLoaderRegistry giải quyết vấn đề gì?

Giả sử schema có quan hệ giữa Book và Author:

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

Root resolver tải danh sách sách:

~~~java
@QueryMapping
public List<Book> books() {
    return bookService.findAll();
}
~~~

Nếu mỗi Book có `authorId`, resolver của field `Book.author` có thể truy vấn Author riêng:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorService.findById(book.authorId());
}
~~~

Khi danh sách có 50 Book, GraphQL có thể gọi resolver author 50 lần. Nếu mỗi lần gọi repository thực hiện một truy vấn, server tạo ra 50 truy vấn bổ sung. Đây là vấn đề N+1.

DataLoader gom các lần gọi `load(authorId)` trong cùng một request thành một batch. Thay vì truy vấn từng Author, batch loader nhận tập ID và tải dữ liệu một lần:

~~~text
Không dùng DataLoader:
Book 1 -> query Author 1
Book 2 -> query Author 2
Book 3 -> query Author 3
...
Book 50 -> query Author 50

Dùng DataLoader:
Book 1 ─┐
Book 2 ─┤
Book 3 ─┼─> DataLoader -> batch query Authors
...     │
Book 50 ─┘
~~~

BatchLoaderRegistry là API Spring for GraphQL dùng để đăng ký các batch function cho cơ chế này.

## 2. BatchLoaderRegistry là gì?

GraphQL Java cung cấp DataLoader và DataLoaderRegistry. Spring for GraphQL bổ sung `BatchLoaderRegistry` để tích hợp việc đăng ký batch loader với vòng đời của GraphQL request.

Vai trò của các thành phần:

| Thành phần | Trách nhiệm |
| --- | --- |
| `BatchLoaderRegistry` | Đăng ký batch loader theo kiểu key/value và cấu hình liên quan. |
| Batch loader | Nhận nhiều key, tải dữ liệu theo lô và trả kết quả. |
| `DataLoader<K, V>` | API resolver dùng để yêu cầu tải dữ liệu theo key. |
| `DataLoaderRegistry` | Chứa các DataLoader được sử dụng trong một GraphQL execution. |
| `BatchLoaderEnvironment` | Cung cấp thông tin môi trường cho batch function, bao gồm context được tích hợp. |

Spring Boot cung cấp `BatchLoaderRegistry` trong cấu hình Spring for GraphQL tiêu chuẩn. Có thể inject registry vào configuration hoặc component và đăng ký loader khi ứng dụng khởi tạo.

Điểm quan trọng là hàm loader được đăng ký ở cấp ứng dụng, còn DataLoader được tạo và sử dụng theo từng GraphQL request. Vì vậy, cache của DataLoader mặc định không phải cache dùng chung giữa tất cả người dùng hoặc mọi request.

## 3. Đăng ký loader theo kiểu key/value

Ví dụ, Book lưu `authorId` kiểu Long và resolver cần lấy Author tương ứng. Có thể đăng ký mapped batch loader:

~~~java
package com.example.catalog.config;

import com.example.catalog.author.Author;
import com.example.catalog.author.AuthorService;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.BatchLoaderRegistry;

@Configuration
public class GraphQlDataLoaderConfig {

    public GraphQlDataLoaderConfig(
            BatchLoaderRegistry registry,
            AuthorService authorService) {

        registry.forTypePair(Long.class, Author.class)
                .registerMappedBatchLoader((authorIds, environment) ->
                        authorService.findAllByIds(authorIds));
    }
}
~~~

Trong ví dụ này, `AuthorService.findAllByIds` trả về `Mono<Map<Long, Author>>`. Map được đánh chỉ mục bằng ID của Author:

~~~java
public Mono<Map<Long, Author>> findAllByIds(Set<Long> authorIds) {
    return authorRepository.findAllByIdIn(authorIds)
            .collectMap(Author::id);
}
~~~

Đoạn service trên giả định repository có phương thức reactive `findAllByIdIn` trả về `Flux<Author>`. Nếu dùng repository đồng bộ, có thể chuyển kết quả đồng bộ sang kiểu reactive phù hợp và thực hiện blocking work trên scheduler dành cho I/O; không chặn event-loop thread.

`forTypePair(Long.class, Author.class)` khai báo kiểu key và value. Khi resolver yêu cầu `DataLoader<Long, Author>`, Spring có thể kết nối với loader đã đăng ký cho cặp kiểu đó.

### Vì sao dùng mapped batch loader?

Batch loader dạng map trả kết quả dưới dạng `Map<K, V>`, mỗi key gắn với value tương ứng. Điều này hữu ích khi thứ tự kết quả từ database không giống thứ tự các key đầu vào.

Ví dụ DataLoader nhận các key:

~~~text
[authorId-8, authorId-2, authorId-5]
~~~

Database có thể trả Author theo thứ tự:

~~~text
[authorId-2, authorId-5, authorId-8]
~~~

Nếu batch function chỉ trả list, nó phải bảo đảm thứ tự phần tử khớp chính xác với thứ tự key. Với mapped loader, kết quả được gắn theo key:

~~~java
Map<Long, Author> authorsById = Map.of(
        2L, author2,
        5L, author5,
        8L, author8
);
~~~

DataLoader sử dụng map để phân phối kết quả về đúng lần gọi `load()`.

Nếu một key không có trong map, kết quả tương ứng không có value và resolver nhận null. Cần xử lý trường hợp đó phù hợp với nullability của field trong schema.

## 4. Batch loader dạng list và dạng map

BatchLoaderRegistry hỗ trợ đăng ký batch loader trả về list hoặc mapped batch loader trả về map.

### Batch loader trả list

~~~java
registry.forTypePair(Long.class, Author.class)
        .registerBatchLoader(authorIds ->
                authorService.findAllByIdsInRequestedOrder(authorIds));
~~~

Với dạng list, batch function nhận danh sách key và phải trả kết quả theo đúng thứ tự tương ứng với danh sách key đầu vào. Nếu database trả dữ liệu theo thứ tự khác, service cần sắp xếp lại theo key trước khi trả.

Ví dụ:

~~~java
public Mono<List<Author>> findAllByIdsInRequestedOrder(List<Long> ids) {
    return authorRepository.findAllByIdIn(ids)
            .collectMap(Author::id)
            .map(byId -> ids.stream()
                    .map(byId::get)
                    .toList());
}
~~~

Ví dụ này minh họa cách khôi phục thứ tự key sau khi repository trả kết quả. Nếu một key không tìm thấy, cần giữ đúng vị trí của key đó và quyết định trả null hay phát sinh lỗi theo hợp đồng của field.

### Mapped batch loader trả map

~~~java
registry.forTypePair(Long.class, Author.class)
        .registerMappedBatchLoader((authorIds, environment) ->
                authorService.findAllByIds(authorIds));
~~~

Dạng map thường dễ sử dụng hơn nếu repository không bảo đảm thứ tự kết quả. Chỉ cần map key đúng với key đã yêu cầu.

Nên ưu tiên mapped loader khi dữ liệu có định danh ổn định và có thể lập chỉ mục theo key. Dùng list loader khi batch function có thể bảo đảm thứ tự tương ứng một cách rõ ràng.

## 5. Inject DataLoader vào resolver

Sau khi đăng ký loader, controller có thể nhận `DataLoader<K, V>` như một tham số method.

Ví dụ model:

~~~java
public record Book(
        Long id,
        String title,
        Long authorId
) {
}

public record Author(
        Long id,
        String name
) {
}
~~~

Resolver:

~~~java
package com.example.catalog.graphql;

import com.example.catalog.author.Author;
import com.example.catalog.book.Book;
import org.dataloader.DataLoader;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

import java.util.concurrent.CompletableFuture;

@Controller
public class BookController {

    @SchemaMapping(typeName = "Book", field = "author")
    public CompletableFuture<Author> author(
            Book book,
            DataLoader<Long, Author> authorLoader) {

        return authorLoader.load(book.authorId());
    }
}
~~~

Spring cung cấp DataLoader phù hợp với kiểu key/value đã đăng ký. Resolver gọi `load()` và trả về `CompletableFuture<Author>`. GraphQL engine chờ kết quả bất đồng bộ để hoàn thành field author.

Không cần gọi repository trực tiếp trong resolver. Việc tải theo lô nằm trong batch function đã đăng ký.

### Luồng xử lý

~~~mermaid
sequenceDiagram
    participant Client
    participant GraphQL as GraphQL Engine
    participant Resolver as Book.author resolver
    participant Loader as DataLoader
    participant Batch as BatchLoaderRegistry function
    participant DB as Author repository

    Client->>GraphQL: Query books { author { name } }
    GraphQL->>Resolver: Resolve author for each Book
    Resolver->>Loader: load(authorId)
    Resolver->>Loader: load(nextAuthorId)
    Resolver->>Loader: load(otherAuthorId)
    GraphQL->>Loader: Dispatch pending keys
    Loader->>Batch: Batch keys
    Batch->>DB: Load authors by IDs
    DB-->>Batch: Authors
    Batch-->>Loader: Map<id, Author>
    Loader-->>Resolver: Complete futures
    Resolver-->>GraphQL: Author values
    GraphQL-->>Client: GraphQL response
~~~

Các lời gọi `load()` được gom trước khi batch function thực thi. Cơ chế dispatch do GraphQL Java điều phối trong quá trình thực thi; trong resolver thông thường không cần tự gọi `dispatch()`.

## 6. Không chặn future của DataLoader

Một lỗi thường gặp là gọi `join()` hoặc `get()` ngay sau `load()`:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book, DataLoader<Long, Author> authorLoader) {
    return authorLoader.load(book.authorId()).join();
}
~~~

Cách này buộc resolver chờ kết quả ngay lập tức. Nếu mỗi resolver chặn như vậy, GraphQL có thể không gom được các key của nhiều Book thành một batch hiệu quả.

Nên trả future:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public CompletableFuture<Author> author(
        Book book,
        DataLoader<Long, Author> authorLoader) {
    return authorLoader.load(book.authorId());
}
~~~

Hoặc kết hợp xử lý bất đồng bộ:

~~~java
return authorLoader.load(book.authorId())
        .thenApply(author -> author);
~~~

Không cần thêm `thenApply` nếu không có bước xử lý nào. Ví dụ thứ hai chỉ minh họa rằng có thể tiếp tục chuỗi xử lý mà vẫn giữ future bất đồng bộ.

Trả future giúp GraphQL engine điều phối việc dispatch và hoàn tất nhiều field cùng lúc. Không nên chuyển kết quả về đồng bộ chỉ để code ngắn hơn.

## 7. DataLoader gom key và cache trong phạm vi request

DataLoader thường có hai hành vi quan trọng:

**Batching:** nhiều lần gọi `load(key)` được gom lại để batch function xử lý cùng lúc.

**Caching theo key:** nếu cùng một key được yêu cầu nhiều lần trong cùng request, DataLoader mặc định có thể dùng lại kết quả đã tải thay vì gọi batch loader lần nữa.

Ví dụ:

~~~java
CompletableFuture<Author> first = authorLoader.load(10L);
CompletableFuture<Author> second = authorLoader.load(10L);
CompletableFuture<Author> third = authorLoader.load(20L);
~~~

Trong cùng request, hai lần gọi key `10L` có thể dùng chung kết quả đã được lên lịch hoặc đã cache. Batch loader thường chỉ cần tải hai key duy nhất là `10L` và `20L`.

Cache này có phạm vi theo DataLoader instance của request. Một request khác có DataLoader riêng và có thể tải dữ liệu mới nhất.

Không nên nhầm DataLoader cache với cache nghiệp vụ lâu dài như Redis hoặc cache của repository. DataLoader giúp tối ưu việc phối hợp tải dữ liệu trong một lần thực thi GraphQL; nó không thay thế chiến lược cache toàn hệ thống.

## 8. Chọn key phù hợp cho batch loader

Key phải đại diện đầy đủ cho các tham số ảnh hưởng đến kết quả tải dữ liệu.

Nếu Author chỉ được tải theo ID, key là `Long` phù hợp:

~~~java
DataLoader<Long, Author>
~~~

Nếu kết quả phụ thuộc thêm ngôn ngữ hoặc tenant, chỉ dùng authorId có thể gây dùng lại kết quả không đúng trong cùng request:

~~~java
public record AuthorLookupKey(
        Long authorId,
        String locale,
        String tenantId
) {
}
~~~

Loader khi đó cần được đăng ký với kiểu key tổng hợp và value tương ứng:

~~~java
registry.forTypePair(AuthorLookupKey.class, Author.class)
        .registerMappedBatchLoader((keys, environment) ->
                authorService.findAllByKeys(keys));
~~~

Service phải nhóm hoặc truy vấn theo đủ các thành phần của key. Với dữ liệu phụ thuộc quyền truy cập, tenant hoặc locale, không được bỏ những yếu tố này khỏi key nếu chúng làm thay đổi kết quả.

Tuy nhiên, không phải lúc nào cũng cần đưa mọi thông tin vào key. Nếu một thông tin được cố định trong GraphQL request và batch function đọc được từ request context, có thể dùng context thay vì lặp lại nó trong từng key. Cần bảo đảm cách thiết kế không làm trộn dữ liệu giữa các request.

## 9. Truyền context vào batch loader

Có trường hợp batch function cần thêm thông tin ngoài key, chẳng hạn locale, tenant hoặc thông tin request. Spring for GraphQL tích hợp GraphQL context với batch loader environment.

Ví dụ, batch function nhận `BatchLoaderEnvironment`:

~~~java
registry.forTypePair(Long.class, Author.class)
        .registerMappedBatchLoader((authorIds, environment) ->
                authorService.findAllByIds(authorIds, environment));
~~~

`BatchLoaderEnvironment` cung cấp ngữ cảnh của batch execution và các thông tin context được thiết lập cho loader. Có thể dùng context để chọn ngôn ngữ hoặc áp dụng chính sách phù hợp cho request hiện tại.

Cần chú ý:

- Context phải được thiết lập từ nguồn đáng tin cậy ở server.
- Không tin tenant hoặc user ID do client tự truyền nếu chưa xác thực.
- Không giữ context của request này trong biến dùng chung cho request khác.
- Nếu dữ liệu trả về khác nhau theo từng key do context riêng của từng lần load, cần thiết kế key/context tương ứng và kiểm tra API DataLoader đang dùng.
- Không dùng context để né kiểm tra authorization ở service.

Với trường hợp đơn giản, không cần context, hãy dùng batch function chỉ nhận tập key. Chỉ bổ sung context khi nghiệp vụ thực sự cần.

## 10. BatchLoaderRegistry và @BatchMapping

Spring for GraphQL có hai cách phổ biến để batch nested field: đăng ký DataLoader qua `BatchLoaderRegistry` hoặc dùng annotation `@BatchMapping`.

### Dùng @BatchMapping

Ví dụ:

~~~java
@Controller
public class BookController {

    private final AuthorService authorService;

    public BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(List<Book> books) {
        return authorService.findForBooks(books);
    }
}
~~~

Phương thức findForBooks cần trả map có key là từng Book trong danh sách đầu vào và value là Author tương ứng. Spring dùng map này để ghép kết quả về đúng source object.

`@BatchMapping` cho Spring biết method này xử lý một nhóm source object cùng lúc. Spring tạo DataLoader tương ứng để kết nối kết quả map với từng Book.

### Khi nào dùng BatchLoaderRegistry?

Dùng `BatchLoaderRegistry` khi:

- Cần DataLoader được dùng từ nhiều resolver hoặc nhiều vị trí.
- Cần kiểm soát key/value type rõ ràng.
- Cần composite key.
- Cần truy cập batch environment hoặc context.
- Cần cấu hình loader ở tầng infrastructure hoặc service.
- Muốn gọi DataLoader tường minh từ controller hoặc data fetcher.

Dùng `@BatchMapping` khi quan hệ giữa một loại source object và một field có logic batch trực tiếp, method nhận danh sách source object và trả kết quả theo từng source.

Hai cách đều dựa trên cơ chế DataLoader của GraphQL Java. Không đăng ký cả `@BatchMapping` và một DataLoader khác để cùng xử lý một field nếu không có chủ đích rõ ràng, vì có thể tạo mapping xung đột hoặc khiến logic khó theo dõi.

## 11. Batch loader xử lý dữ liệu không tồn tại và lỗi

Batch function phải xác định cách xử lý key không tìm thấy.

Với mapped loader, nếu map không có một key, DataLoader không có value tương ứng và kết quả cho key đó là null. Điều này phù hợp nếu field trong SDL nullable:

~~~graphql
type Book {
    author: Author
}
~~~

Nếu schema khai báo:

~~~graphql
type Book {
    author: Author!
}
~~~

thì kết quả null có thể gây GraphQL execution error và null propagation. Hãy bảo đảm loader trả đủ dữ liệu hoặc có quy tắc lỗi phù hợp.

Nếu toàn bộ batch function gặp lỗi, có thể trả `Mono.error(...)` hoặc để reactive pipeline phát sinh lỗi:

~~~java
registry.forTypePair(Long.class, Author.class)
        .registerMappedBatchLoader((authorIds, environment) ->
                authorService.findAllByIds(authorIds)
                        .onErrorMap(
                                DataAccessException.class,
                                AuthorBatchLoadException::new
                        ));
~~~

Ví dụ trên minh họa chuyển đổi lỗi dữ liệu. GraphQL sẽ ghi nhận lỗi trong quá trình resolve các field phụ thuộc vào loader. Hãy kiểm tra error path và exception handling của ứng dụng để client nhận thông tin an toàn.

Không nên biến mọi lỗi truy vấn thành map rỗng. Làm như vậy có thể khiến lỗi database bị hiểu nhầm thành “không có Author”. Chỉ trả kết quả rỗng khi đó thực sự là ngữ nghĩa của dữ liệu.

## 12. Giới hạn batch size và tải dữ liệu lớn

Một operation có thể yêu cầu rất nhiều key. Batch loader nên giới hạn lượng dữ liệu xử lý trong một lần để tránh truy vấn quá lớn hoặc vượt giới hạn của database.

Có thể chia key thành nhóm nhỏ trong service:

~~~java
public Mono<Map<Long, Author>> findAllByIds(Set<Long> ids) {
    return Flux.fromIterable(ids)
            .buffer(500)
            .concatMap(authorRepository::findAllByIdIn)
            .flatMapIterable(authors -> authors)
            .collectMap(Author::id);
}
~~~

Ví dụ giả định repository có phương thức nhận collection ID và trả về Flux Author. Kích thước 500 chỉ là con số minh họa; cần điều chỉnh theo database, giới hạn câu lệnh, kích thước response và tải thực tế.

Cũng cần giới hạn ở cấp API:

- Page size tối đa cho danh sách.
- Độ sâu hoặc độ phức tạp của query theo chính sách server.
- Số lượng phần tử được phép tải theo một operation.
- Timeout và giới hạn tài nguyên cho truy vấn dữ liệu.

DataLoader giảm số lần truy vấn, nhưng không làm cho một query không giới hạn trở nên an toàn hoặc rẻ. Batch lớn vẫn có thể tiêu tốn nhiều bộ nhớ và thời gian.

## 13. Kiểm thử BatchLoaderRegistry

Nên kiểm thử cả kết quả trả về lẫn số lần batch function được gọi.

Ví dụ GraphQL operation:

~~~graphql
query {
    books {
        id
        author {
            id
            name
        }
    }
}
~~~

Test có thể dùng GraphQlTester:

~~~java
@Test
void loadsAuthorsForBooksThroughBatchLoader() {
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
        .isEqualTo("Ada");
}
~~~

Đây là ví dụ cấu trúc test; test context cần nạp schema, controller, `BatchLoaderRegistry` và dữ liệu/service tương ứng.

Các trường hợp nên kiểm thử:

- Một Book có Author hợp lệ.
- Nhiều Book tham chiếu nhiều Author khác nhau.
- Nhiều Book cùng tham chiếu một Author.
- Một authorId không tồn tại.
- Batch function trả map thiếu một key.
- Batch function phát sinh lỗi.
- Key tổng hợp có locale hoặc tenant khác nhau.
- DataLoader cache hoạt động trong cùng request.
- Hai request độc lập không dùng chung cache của nhau.
- Số lần gọi repository giảm khi số Book tăng.

Có thể dùng mock hoặc spy service để xác nhận `findAllByIds` nhận tập key duy nhất theo batch. Một test chỉ xác nhận response đúng chưa đủ chứng minh N+1 đã được loại bỏ; cần kiểm tra số lần gọi batch service hoặc repository.

## 14. Các lỗi thường gặp khi dùng BatchLoaderRegistry

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Resolver không nhận được DataLoader | Chưa đăng ký đúng cặp kiểu key/value hoặc generic không khớp. | Đối chiếu `forTypePair` với `DataLoader<K, V>`. |
| Batch function không được gọi | Resolver không gọi `load()` hoặc field không nằm trong selection set. | Kiểm tra operation và nested resolver. |
| Vẫn phát sinh N+1 | Resolver gọi repository trực tiếp thay vì DataLoader. | Trả future từ `load()` và để batch function truy vấn theo lô. |
| Batch loader list trả sai dữ liệu | Thứ tự list không khớp thứ tự key đầu vào. | Sắp xếp lại theo key hoặc dùng mapped batch loader. |
| Một số field trả null | Map không có key tương ứng hoặc repository không tìm thấy dữ liệu. | Kiểm tra key, missing data và nullability SDL. |
| Trả nhầm dữ liệu giữa điều kiện khác nhau | Key không bao gồm tham số ảnh hưởng kết quả. | Dùng composite key hoặc context phù hợp. |
| Dữ liệu cũ trong cùng request | DataLoader cache đã lưu kết quả theo key. | Cân nhắc clear/prime sau mutation nếu cần đọc lại trong cùng request. |
| Cache dùng chung giữa người dùng | Tự tạo DataLoader hoặc cache ở phạm vi singleton. | Dùng registry tích hợp theo request và tránh chia sẻ instance mutable. |
| Batch query quá lớn | Không giới hạn kích thước batch hoặc query complexity. | Chia batch, giới hạn page size và theo dõi tải. |
| Lỗi repository bị hiểu là không có dữ liệu | Batch function nuốt exception và trả map rỗng. | Giữ lỗi để GraphQL error handling xử lý đúng. |

## 15. Quy trình triển khai BatchLoaderRegistry

Khi cần thêm batch loader, có thể đi theo trình tự:

1. Xác định nested field nào đang tạo nhiều truy vấn.
2. Xác định key tối thiểu và kiểu value mà resolver cần.
3. Chọn mapped batch loader hoặc list batch loader.
4. Đăng ký bằng `BatchLoaderRegistry.forTypePair`.
5. Đảm bảo batch function tải theo lô và trả kết quả đúng key.
6. Inject `DataLoader<K, V>` vào resolver.
7. Gọi `load(key)` và trả future, không chặn bằng join/get.
8. Kiểm tra missing key, lỗi, context và authorization.
9. Xác định cache key có bao gồm mọi yếu tố ảnh hưởng kết quả không.
10. Giới hạn batch size và query complexity.
11. Dùng GraphQlTester kiểm tra kết quả và số lần gọi batch.
12. So sánh số truy vấn trước và sau khi áp dụng DataLoader.

## 16. Những điểm cần ghi nhớ

- `BatchLoaderRegistry` là API Spring for GraphQL để đăng ký batch loader tích hợp với DataLoader.
- `forTypePair(keyType, valueType)` liên kết kiểu key/value của loader với DataLoader được resolver sử dụng.
- Mapped batch loader trả `Map<K, V>`, giúp ánh xạ kết quả theo key mà không phụ thuộc thứ tự database.
- List batch loader phải giữ đúng thứ tự tương ứng với key đầu vào.
- Resolver gọi `DataLoader.load()` và nên trả future để GraphQL điều phối batching.
- DataLoader gom key và cache trong phạm vi request; nó không thay thế cache dùng chung của ứng dụng.
- Composite key hoặc context cần phản ánh đầy đủ điều kiện ảnh hưởng đến kết quả.
- `@BatchMapping` là lựa chọn tiện lợi cho quan hệ source-field đơn giản; BatchLoaderRegistry phù hợp khi cần DataLoader tường minh và tái sử dụng.
- Phải xử lý key không tồn tại, batch error, authorization và giới hạn batch size.
- Kiểm thử cả dữ liệu trả về lẫn số lần gọi batch để xác nhận hiệu quả.

BatchLoaderRegistry giúp Spring for GraphQL kết nối resolver với batch loading một cách nhất quán. Khi đăng ký đúng key/value, trả kết quả đúng từng key và giữ resolver bất đồng bộ, ứng dụng có thể giảm truy vấn N+1 mà vẫn bảo toàn ngữ nghĩa của từng field và từng request.

