# Mapped batch loader

## 1. Mapped batch loader giải quyết vấn đề gì?

Khi client truy vấn danh sách sách và mỗi sách có field `author`, resolver của field này có thể phải tải tác giả tương ứng. Nếu resolver gọi repository riêng cho từng quyển sách, một query lấy 50 sách có thể tạo thêm 50 truy vấn lấy tác giả. Đây là vấn đề N+1.

DataLoader gom các yêu cầu tải dữ liệu phát sinh trong cùng một GraphQL execution. Resolver gọi `load(key)` và nhận về một future; DataLoader thu thập các key rồi gọi batch loader để tải nhiều giá trị trong một lần. Cơ chế cache theo request còn giúp tránh tải lặp lại cùng một key trong một execution.

Spring for GraphQL cung cấp `BatchLoaderRegistry` để đăng ký các batch loading function và tự tạo DataLoader cho từng request. Trong số các lựa chọn đăng ký, `registerMappedBatchLoader` phù hợp khi kết quả được trả về dưới dạng `Map<K, V>` ánh xạ trực tiếp từ key sang giá trị.

Mapped batch loader đặc biệt hữu ích khi repository trả về dữ liệu theo thứ tự riêng, khi một số key không có bản ghi tương ứng, hoặc khi muốn biểu diễn quan hệ bằng một map thay vì phải tự sắp xếp danh sách kết quả theo thứ tự key đầu vào.

## 2. Phân biệt batch loader dạng list và mapped batch loader

Spring for GraphQL hỗ trợ hai kiểu đăng ký phổ biến:

| Cơ chế | Đầu vào batch | Kết quả | Yêu cầu quan trọng |
| --- | --- | --- | --- |
| `registerBatchLoader` | `List<K>` | `Flux<V>` | Kết quả phải có cùng số lượng và đúng thứ tự với danh sách key đầu vào; dùng `null` cho key không có giá trị |
| `registerMappedBatchLoader` | `Set<K>` | `Mono<Map<K, V>>` | Mỗi giá trị được gắn với key tương ứng; không cần phụ thuộc thứ tự kết quả |

Ví dụ, DataLoader nhận các key tác giả `a1`, `a2`, `a3`. Repository có thể trả về tác giả theo thứ tự `a3`, `a1`; với list batch loader, ứng dụng phải sắp xếp lại kết quả đúng thành `a1`, `a2`, `a3`. Với mapped batch loader, chỉ cần trả map:

```java
Map<String, Author> authors = Map.of(
    "a1", authorA1,
    "a3", authorA3
);
```

DataLoader tra từng key trong map. Key `a2` không có entry nên kết quả tương ứng là `null`. Đây là lý do mapped batch loader thuận tiện với các truy vấn `IN (...)` mà database không bảo đảm thứ tự trả về.

## 3. Thiết kế schema và mô hình dữ liệu ví dụ

Giả sử một query trả về danh sách sách, mỗi sách tham chiếu đến tác giả bằng `authorId`:

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

Field `Book.author` được khai báo nullable vì dữ liệu có thể không có tác giả hoặc tác giả đã bị xóa. Nếu nghiệp vụ bảo đảm mọi sách đều có tác giả hợp lệ, có thể cân nhắc `Author!`, nhưng khi đó batch loader phải bảo đảm không có key nào thiếu kết quả.

Mô hình Java minh họa:

```java
public record Book(
    String id,
    String title,
    String authorId) {
}

public record Author(
    String id,
    String name) {
}
```

Query của client:

```graphql
query BookCatalog {
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

GraphQL engine phân giải `Query.books` trước. Sau đó, với mỗi `Book`, engine cần phân giải field `author`. DataLoader giúp gom các `authorId` lại để tải nhiều tác giả cùng lúc.

## 4. Tạo service trả về Map theo key

Mapped batch loader cần trả về một map có key là định danh đã yêu cầu và value là đối tượng tương ứng. Với Spring Data JPA, repository có thể khai báo như sau:

```java
import org.springframework.data.jpa.repository.JpaRepository;

public interface AuthorRepository extends JpaRepository<AuthorEntity, String> {
}
```

Service dùng repository để tải tất cả tác giả theo một tập ID:

```java
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.stereotype.Service;

@Service
public class AuthorQueryService {

    private final AuthorRepository authorRepository;
    private final AuthorMapper authorMapper;

    public AuthorQueryService(
            AuthorRepository authorRepository,
            AuthorMapper authorMapper) {
        this.authorRepository = authorRepository;
        this.authorMapper = authorMapper;
    }

    public Map<String, Author> findAllByIds(Set<String> ids) {
        if (ids.isEmpty()) {
            return Map.of();
        }

        return authorRepository.findAllById(ids).stream()
            .map(authorMapper::toDomain)
            .collect(Collectors.toMap(Author::id, Function.identity()));
    }
}
```

`AuthorRepository` có thể là Spring Data repository, còn `AuthorMapper` chuyển entity persistence thành kiểu domain `Author`. Service trả map được đánh chỉ mục theo `Author.id`, vì đây là key mà resolver sẽ gửi vào DataLoader.

Không giả định thứ tự của `findAllById`. Với mapped batch loader, map mới là hợp đồng quan trọng; mỗi entry phải dùng đúng ID. Nếu repository trả một bản ghi có ID không nằm trong tập yêu cầu, hãy kiểm tra lại query hoặc mapping thay vì đưa entry đó vào map một cách tùy tiện.

## 5. Đăng ký mapped batch loader bằng `BatchLoaderRegistry`

Spring Boot cung cấp bean `BatchLoaderRegistry`. Có thể inject registry vào một cấu hình và đăng ký loader trong constructor:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.BatchLoaderRegistry;
import reactor.core.publisher.Mono;

@Configuration
public class GraphQlDataLoaderConfig {

    public GraphQlDataLoaderConfig(
            BatchLoaderRegistry registry,
            AuthorQueryService authorQueryService) {

        registry.forTypePair(String.class, Author.class)
            .registerMappedBatchLoader((authorIds, environment) ->
                Mono.fromCallable(() ->
                    authorQueryService.findAllByIds(authorIds)
                )
            );
    }
}
```

`forTypePair(String.class, Author.class)` đăng ký loader với key kiểu `String` và value kiểu `Author`. `registerMappedBatchLoader` nhận một hàm với tập key và `BatchLoaderEnvironment`, rồi trả về `Mono<Map<String, Author>>`.

Spring for GraphQL dùng registry này để đăng ký DataLoader vào `DataLoaderRegistry` của từng GraphQL request. Ứng dụng không cần tự tạo một DataLoader singleton dùng chung giữa mọi request.

Trong ví dụ, `Mono.fromCallable` trì hoãn lời gọi service đến khi publisher được subscribe. Nếu service dùng JPA/JDBC blocking trong ứng dụng reactive, cần đưa phần blocking sang scheduler phù hợp, chẳng hạn `Schedulers.boundedElastic()`. Bọc một lời gọi blocking trong `Mono` không tự biến truy vấn database thành non-blocking. Nếu service/repository đã reactive, hãy trả về publisher reactive của nó thay vì bọc một lời gọi blocking.

Ví dụ với service đã trả `Mono<Map<String, Author>>`:

```java
registry.forTypePair(String.class, Author.class)
    .registerMappedBatchLoader((authorIds, environment) ->
        authorReactiveQueryService.findAllByIds(authorIds)
    );
```

## 6. Dùng DataLoader trong `@SchemaMapping`

Sau khi đăng ký, resolver có thể nhận DataLoader qua tham số phương thức:

```java
import java.util.concurrent.CompletableFuture;
import org.dataloader.DataLoader;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookFieldController {

    @SchemaMapping(typeName = "Book", field = "author")
    public CompletableFuture<Author> author(
            Book book,
            DataLoader<String, Author> authorLoader) {

        if (book.authorId() == null) {
            return CompletableFuture.completedFuture(null);
        }

        return authorLoader.load(book.authorId());
    }
}
```

`authorLoader.load(book.authorId())` không nhất thiết truy vấn database ngay tại dòng đó. Nó xếp key vào DataLoader và trả về `CompletableFuture<Author>`. GraphQL Java quản lý thời điểm dispatch các key đã được gom và hoàn tất future khi batch loader trả kết quả.

Khi đăng ký bằng `forTypePair`, tên DataLoader mặc định dựa trên tên class của value type. Spring for GraphQL có thể suy ra loader từ kiểu generic `DataLoader<String, Author>` trong tham số resolver, vì vậy thường không cần chỉ định tên thủ công.

Nếu field `author` được khai báo `Author` nullable, một key không có kết quả có thể trả `null`. Nếu field là `Author!`, kết quả null sẽ vi phạm non-null contract và GraphQL tạo lỗi thực thi với null propagation tương ứng.

## 7. Mapped batch loader xử lý key không có dữ liệu

Giả sử DataLoader nhận tập key `{a1, a2, a3}` nhưng database chỉ có `a1` và `a3`. Mapped batch loader trả:

```java
Map<String, Author> result = Map.of(
    "a1", authorA1,
    "a3", authorA3
);
```

Key `a2` không có entry trong map. DataLoader sẽ trả `null` cho lần load tương ứng. Điều này khác với batch loader dạng list, nơi ứng dụng phải trả một phần tử `null` đúng vị trí của key bị thiếu.

Quyết định xử lý key thiếu phải phù hợp với schema và nghiệp vụ:

- Quan hệ tùy chọn: field có thể nullable và map không có entry.
- Quan hệ bắt buộc: dữ liệu thiếu cần được xem là lỗi toàn vẹn hoặc lỗi nghiệp vụ; không nên âm thầm coi là thành công.
- Không có `authorId` ở parent: resolver có thể trả future hoàn tất với `null` mà không gọi `load(null)`.
- ID không hợp lệ: kiểm tra hoặc từ chối theo quy tắc domain trước khi truy vấn nếu cần.

Không tạo một object `Author` giả chỉ để lấp key còn thiếu. Làm như vậy khiến client nhận dữ liệu sai và che giấu lỗi liên kết dữ liệu.

## 8. Mapped batch loader không phụ thuộc thứ tự kết quả

Đây là điểm khác biệt quan trọng so với `registerBatchLoader` dạng list.

Giả sử resolver yêu cầu các ID theo thứ tự:

```text
["a1", "a2", "a3"]
```

Database có thể trả:

```text
[Author("a3"), Author("a1")]
```

Với list batch loader, nếu trả trực tiếp danh sách này thì DataLoader có thể ghép sai tác giả với sách vì kết quả phải theo đúng thứ tự key đầu vào. Với mapped batch loader, service tạo map:

```java
Map<String, Author> result = Map.of(
    "a3", authorA3,
    "a1", authorA1
);
```

DataLoader tra kết quả theo key nên không quan tâm thứ tự iteration của map. `a2` không có entry và nhận `null`. Đây là lợi ích lớn khi dùng các truy vấn database dạng `WHERE id IN (...)`, vì nhiều database không cam kết thứ tự trả bản ghi nếu không có `ORDER BY`.

## 9. Cache theo request và key trùng lặp

DataLoader có cache theo request. Nếu nhiều sách cùng tham chiếu tác giả `a1`, resolver có thể gọi `load("a1")` nhiều lần nhưng DataLoader mặc định có thể dùng lại kết quả đã yêu cầu cho key đó trong cùng execution.

Ví dụ:

```text
Book 1 -> authorId = a1
Book 2 -> authorId = a1
Book 3 -> authorId = a2
Book 4 -> authorId = a3
```

Các lần gọi `load` có thể được gom thành một batch với các key duy nhất `a1`, `a2`, `a3`. Nhờ vậy, database chỉ cần tải mỗi tác giả một lần trong batch đó.

Cache mặc định tồn tại trong phạm vi DataLoader của request, không phải cache dùng chung lâu dài cho toàn ứng dụng. Không tự tạo DataLoader singleton để lưu dữ liệu qua nhiều người dùng vì dữ liệu có thể phụ thuộc tenant, quyền truy cập hoặc trạng thái cập nhật.

Nếu một Mutation cập nhật dữ liệu rồi operation cần đọc lại cùng key trong cùng execution, hãy xem xét xóa key khỏi cache hoặc prime giá trị mới theo API DataLoader phù hợp. Nếu không, lần load tiếp theo có thể nhận giá trị đã được cache trước khi cập nhật.

## 10. Tùy chỉnh tên loader và DataLoaderOptions

Khi dùng `forTypePair`, Spring for GraphQL mặc định đặt tên loader dựa trên class của kiểu value. Đây là cách thuận tiện khi một loại entity chỉ cần một loader chính.

Nếu cần nhiều loader cùng trả về một kiểu value nhưng có mục đích hoặc key type khác nhau, có thể đăng ký theo tên:

```java
registry.<String, Author>forName("authorsById")
    .registerMappedBatchLoader((ids, environment) ->
        Mono.fromCallable(() -> authorQueryService.findAllByIds(ids))
    );
```

Khi dùng `forName`, tên tham số DataLoader trong phương thức resolver cần khớp với tên đã đăng ký:

```java
@SchemaMapping(typeName = "Book", field = "author")
public CompletableFuture<Author> author(
        Book book,
        DataLoader<String, Author> authorsById) {
    return authorsById.load(book.authorId());
}
```

Ví dụ này minh họa tên loader tùy chỉnh; trong cấu hình thực tế, hãy giữ cùng tên `authorsById` ở registration và method parameter. Nếu chỉ có một loader cho `Author`, `forTypePair` thường đơn giản hơn.

Có thể cấu hình `DataLoaderOptions` khi cần giới hạn kích thước batch hoặc điều chỉnh cache:

```java
registry.forTypePair(String.class, Author.class)
    .withOptions(options -> options.setMaxBatchSize(100))
    .registerMappedBatchLoader((ids, environment) ->
        Mono.fromCallable(() -> authorQueryService.findAllByIds(ids))
    );
```

`maxBatchSize` giới hạn số key trong một batch. Giới hạn này hữu ích khi database có giới hạn số bind parameter hoặc truy vấn `IN` quá lớn. Nếu DataLoader có nhiều key hơn mức tối đa, GraphQL Java có thể chia thành nhiều batch. Chọn giới hạn dựa trên khả năng database và chi phí truy vấn thực tế.

Chữ ký của callback `withOptions` phụ thuộc phiên bản `java-dataloader` được Spring GraphQL quản lý. Nếu phiên bản dự án dùng `DataLoaderOptions` trực tiếp thay vì builder callback, tạo options theo API của phiên bản đó rồi truyền vào overload `withOptions(DataLoaderOptions)`.

## 11. Dùng GraphQLContext trong mapped batch loader

Mapped batch loader nhận `BatchLoaderEnvironment` bên cạnh tập key. Môi trường này cho phép truy cập context của GraphQL execution. Spring for GraphQL tích hợp `BatchLoaderRegistry` để batch loader và resolver có thể truy cập cùng `GraphQLContext`, đồng thời hỗ trợ context propagation.

Điều này hữu ích khi truy vấn phụ thuộc vào:

- Tenant hiện tại.
- Locale hoặc ngôn ngữ hiển thị.
- Thông tin correlation để tracing.
- Phạm vi dữ liệu mà người dùng hiện tại được phép xem.

Ví dụ về ý tưởng xử lý tenant:

```java
registry.forTypePair(String.class, Author.class)
    .registerMappedBatchLoader((ids, environment) -> {
        GraphQLContext context = environment.getContext();
        String tenantId = context.get("tenantId");

        return Mono.fromCallable(() ->
            authorQueryService.findAllByIdsAndTenant(ids, tenantId)
        );
    });
```

`tenantId` cần được đưa vào `GraphQLContext` từ bước xử lý request hoặc interceptor phù hợp. Batch service vẫn phải áp dụng điều kiện tenant ở phía server; không tin tenant ID do client truyền qua argument nếu người dùng không có quyền chọn tenant đó.

Vì loader được đăng ký theo request, cache không bị chia sẻ giữa các request khác tenant. Tuy nhiên, trong cùng một request, nếu một DataLoader phục vụ nhiều ngữ cảnh quyền khác nhau theo từng key, cần đưa thông tin phân biệt vào key hoặc thiết kế loader riêng để tránh dùng chung kết quả không phù hợp.

## 12. Phân biệt mapped batch loader và `@BatchMapping`

`@BatchMapping` là cách viết ngắn gọn cho trường hợp phổ biến: một field của object cần được tải theo batch từ danh sách source object. Spring for GraphQL tự đăng ký batch loading function và data fetcher cho field đó.

| Tiêu chí | `registerMappedBatchLoader` | `@BatchMapping` |
| --- | --- | --- |
| Đầu vào | Tập key do resolver gửi vào DataLoader | Danh sách source/parent object |
| Kết quả | `Mono<Map<K, V>>` | Thường là `Mono<Map<Source, Value>>` hoặc dạng list/Flux có thứ tự phù hợp |
| Nơi đăng ký | `BatchLoaderRegistry` | Annotation trên controller method |
| Phù hợp | Dùng loader từ nhiều resolver, cần key riêng, cần context hoặc options | Batch một field quan hệ theo source object với ít boilerplate |
| Resolver riêng | Cần `@SchemaMapping` gọi `DataLoader.load` | Spring tự đăng ký data fetcher cho field |

Ví dụ `@BatchMapping`:

```java
@Controller
public class BookBatchController {

    private final AuthorQueryService authorQueryService;

    public BookBatchController(AuthorQueryService authorQueryService) {
        this.authorQueryService = authorQueryService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Mono<Map<Book, Author>> author(List<Book> books) {
        Set<String> ids = books.stream()
            .map(Book::authorId)
            .filter(Objects::nonNull)
            .collect(Collectors.toSet());

        return Mono.fromSupplier(() -> authorQueryService.findAllByIds(ids))
            .map(authorsById -> books.stream()
                .filter(book -> authorsById.containsKey(book.authorId()))
                .collect(Collectors.toMap(
                    Function.identity(),
                    book -> authorsById.get(book.authorId())
                )));
    }
}
```

Ở đây map dùng `Book` làm key, nên `Book` cần triển khai `equals` và `hashCode` ổn định để làm khóa. Vì `Book` là record trong ví dụ nên Java tự sinh hai phương thức này dựa trên các thành phần record. Nếu service dùng JPA/JDBC blocking trong ứng dụng reactive, hãy offload phần truy vấn sang scheduler phù hợp; `Mono.fromSupplier` tự nó không biến thao tác blocking thành non-blocking. Nếu cần DataLoader theo ID và dùng chung từ nhiều resolver, `registerMappedBatchLoader` thường phù hợp hơn.

Không đăng ký cả `@BatchMapping` và một `@SchemaMapping`/DataLoader thủ công cho cùng một cặp type/field. Hãy chọn một cơ chế làm chủ field.

## 13. Xử lý lỗi, missing value và dữ liệu không nhất quán

Mapped batch loader có thể gặp nhiều loại tình huống khác nhau:

- **Không tìm thấy một key:** không đưa key đó vào map; DataLoader trả `null` cho key đó.
- **Không tìm thấy toàn bộ key:** trả `Map.of()`; các load tương ứng đều nhận `null`.
- **Database hoặc service gặp lỗi:** trả publisher lỗi hoặc để exception được chuyển thành lỗi của batch; cần có cơ chế xử lý GraphQL error phù hợp.
- **Dữ liệu liên kết bị hỏng:** ví dụ `Book.authorId` trỏ đến tác giả không tồn tại. Hãy quyết định đây là quan hệ nullable hay lỗi toàn vẹn dữ liệu.
- **Một key xuất hiện nhiều lần:** DataLoader mặc định cache theo key trong request, giảm tải lặp.

Không biến lỗi hạ tầng thành map rỗng. Nếu database đang lỗi, trả map rỗng sẽ khiến client hiểu nhầm rằng tất cả tác giả đều không tồn tại. Hãy để lỗi được truyền qua cơ chế error handling để client và observability nhận biết sự cố.

Với field non-null, một missing value có thể kích hoạt null propagation. Nếu nghiệp vụ không chấp nhận missing value, hãy kiểm tra tính toàn vẹn dữ liệu hoặc trả lỗi có chủ đích thay vì để lỗi nullability xuất hiện ngẫu nhiên.

## 14. Kiểm thử mapped batch loader

Nên kiểm thử hai phần: logic batch function và GraphQL operation sử dụng DataLoader.

### Kiểm thử mapping key sang value

Với input keys `a1`, `a2`, `a3`, kiểm tra rằng:

- Map có `a1` và `a3` nếu repository tìm thấy hai tác giả.
- `a2` không có entry và load tương ứng cho kết quả null.
- Kết quả không phụ thuộc thứ tự trả về của repository.
- Repository được gọi theo batch thay vì một lần cho mỗi key.
- Tập key rỗng trả map rỗng mà không gọi database không cần thiết.

### Kiểm thử GraphQL bằng `GraphQlTester`

Ví dụ operation:

```java
@SpringBootTest
@AutoConfigureHttpGraphQlTester
class BookAuthorBatchTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void loadsAuthorsForBooksInOneBatch() {
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
}
```

Ví dụ giả định test context có ít nhất một sách do tác giả `Nguyen An` viết. Để chứng minh batching thực sự hoạt động, hãy dùng spy hoặc counter ở service/repository và xác nhận một operation có nhiều sách chỉ gọi phương thức tải tác giả theo batch với số lần dự kiến. Chỉ kiểm tra response đúng chưa chứng minh N+1 đã được loại bỏ.

Nên bổ sung các ca kiểm thử:

- Nhiều sách có cùng `authorId`.
- Nhiều sách có các `authorId` khác nhau.
- Một hoặc nhiều tác giả không tồn tại.
- `authorId` của sách là null.
- Batch có số key vượt giới hạn `maxBatchSize`.
- Lỗi repository trong batch.
- Hai request khác tenant không dùng chung dữ liệu cache.
- Field nullable và non-null xử lý missing value đúng hợp đồng.

## 15. Lỗi thường gặp khi dùng mapped batch loader

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Resolver không tìm thấy DataLoader | Key/value type không khớp hoặc loader name không đúng | Đối chiếu `forTypePair`, generic của `DataLoader<K,V>` hoặc tên `forName` |
| Field luôn null | Map dùng sai key, key Java khác kiểu hoặc repository không tìm thấy dữ liệu | Bảo đảm key trong map khớp chính xác key được `load` |
| Tác giả bị gán nhầm cho sách | Tự dùng list batch loader nhưng không giữ thứ tự key | Dùng mapped loader hoặc sắp xếp list đúng thứ tự |
| N+1 vẫn xảy ra | Resolver gọi repository trực tiếp thay vì `DataLoader.load` | Đăng ký batch loader và chuyển resolver sang DataLoader |
| Loader không được đăng ký trong request | Không dùng `BatchLoaderRegistry` được Spring quản lý hoặc cấu hình GraphQL tùy chỉnh bỏ qua registry | Kiểm tra registry được inject và được áp dụng vào execution service |
| Không có kết quả nhưng GraphQL báo lỗi non-null | SDL khai báo field non-null trong khi map thiếu key | Điều chỉnh nullability hoặc bảo đảm quan hệ bắt buộc tồn tại |
| Database bị truy vấn với tập ID quá lớn | Batch không có giới hạn kích thước | Cấu hình `maxBatchSize` phù hợp |
| Dữ liệu sai tenant | Batch query không áp dụng tenant/authorization từ server context | Lấy context đáng tin cậy và lọc trong service/repository |
| Database lỗi nhưng client nhận null | Exception bị nuốt và chuyển thành map rỗng | Chỉ dùng map rỗng cho missing data; truyền lỗi hạ tầng đúng cách |
| Cache trả dữ liệu cũ sau Mutation | DataLoader đã cache key trước khi dữ liệu được cập nhật | Clear hoặc prime key sau thao tác ghi nếu cần đọc lại trong cùng request |

## 16. Checklist triển khai mapped batch loader

- [ ] Xác định rõ quan hệ N+1 cần batch và key dùng để tải dữ liệu.
- [ ] Chọn `registerMappedBatchLoader` khi kết quả tự nhiên là map key-value.
- [ ] Key type và value type khớp với resolver `DataLoader<K, V>`.
- [ ] Batch function nhận `Set<K>` và trả `Mono<Map<K, V>>`.
- [ ] Map được lập chỉ mục bằng đúng key mà resolver đã gửi.
- [ ] Missing key được xử lý theo nullability và quy tắc nghiệp vụ.
- [ ] Resolver gọi `DataLoader.load` và trả future thay vì truy vấn từng parent.
- [ ] Dùng `BatchLoaderRegistry` để loader được đăng ký theo request.
- [ ] Không chia sẻ DataLoader cache toàn cục giữa nhiều request.
- [ ] Giới hạn kích thước batch theo khả năng database.
- [ ] Batch query áp dụng tenant và authorization ở phía server.
- [ ] Kiểm thử thứ tự không phụ thuộc, missing key, duplicate key, lỗi và số lần truy vấn.
- [ ] Chọn `@BatchMapping` nếu chỉ cần batch một field theo parent và không cần cấu hình loader riêng.

## Kết luận

Mapped batch loader trong Spring for GraphQL cho phép tải nhiều entity theo tập key và trả kết quả dưới dạng `Map<K, V>`. `BatchLoaderRegistry.forTypePair(...).registerMappedBatchLoader(...)` đăng ký hàm batch; resolver nhận `DataLoader<K, V>` và gọi `load(key)`. DataLoader gom các key trong cùng GraphQL request, quản lý cache theo request và ghép kết quả theo key nên không phụ thuộc thứ tự dữ liệu repository trả về.

Hãy dùng mapped loader khi cần ánh xạ key-value rõ ràng, xử lý key thiếu hoặc tái sử dụng loader giữa nhiều resolver. Thiết kế map đúng key, quyết định nullability trong SDL, giới hạn kích thước batch, áp dụng tenant/authorization trong batch query và kiểm thử số lần truy vấn thực tế. Với trường hợp chỉ cần batch một field quan hệ đơn giản, `@BatchMapping` có thể là cách viết ngắn gọn hơn.

## Tài liệu tham khảo

- [Spring for GraphQL — Request Execution: Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html#execution.graphql-datafetcher.batch-loading)
- [Spring for GraphQL — BatchLoaderRegistry API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/execution/BatchLoaderRegistry.html)
- [Spring for GraphQL — `@BatchMapping`](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.schema-mapping.batch-mapping)
