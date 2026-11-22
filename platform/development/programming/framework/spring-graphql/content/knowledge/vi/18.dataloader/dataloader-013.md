# Tránh DataLoader dùng state toàn cục trong Spring for GraphQL

`DataLoader` giúp gom nhiều lần tải dữ liệu thành một batch và cache kết quả trong phạm vi một lần thực thi GraphQL. Để cơ chế này an toàn, mỗi GraphQL execution cần có `DataLoaderRegistry` và các `DataLoader` riêng. Không lưu một `DataLoader`, `DataLoaderRegistry` hoặc cache chứa dữ liệu theo request trong biến `static` hay singleton dùng chung giữa nhiều request.

Trong Spring for GraphQL, nên đăng ký batch loader qua `BatchLoaderRegistry` hoặc dùng `@BatchMapping`. `BatchLoaderRegistry` có thể là bean singleton vì nó giữ **định nghĩa đăng ký**; Spring tạo registry và DataLoader instances cho từng GraphQL execution. Sự khác biệt giữa nơi khai báo loader và nơi lưu state của loader là nền tảng để tránh rò rỉ dữ liệu giữa người dùng, tenant và request.

## 1. DataLoader lưu state nào?

Một `DataLoader<K, V>` thường giữ các thành phần sau trong suốt vòng đời của nó:

- Các key đang chờ được gửi đến batch loader.
- Promise/future tương ứng với từng lần gọi `load(key)`.
- Cache kết quả theo key, nếu caching được bật.
- Các tùy chọn batching và cache key.

Ví dụ, resolver của 20 quyển sách gọi `authorLoader.load(authorId)` để tải tác giả. DataLoader có thể gom các ID vào một batch, gọi service một lần rồi phân phối kết quả về từng resolver. Nếu cùng một ID được yêu cầu nhiều lần trong cùng execution và cache đang bật, DataLoader có thể dùng lại kết quả đã có.

State này phụ thuộc vào request: danh sách key cần tải, kết quả cache và thời điểm dispatch đều thuộc một lần thực thi GraphQL cụ thể. Vì vậy, không thể dùng một instance chung cho nhiều request độc lập.

## 2. Vì sao không dùng DataLoader toàn cục?

Một anti-pattern là tạo DataLoader trong field `static` hoặc trong singleton service rồi giữ nó cho mọi request:

~~~java
import org.dataloader.DataLoader;
import org.dataloader.DataLoaderFactory;
import org.springframework.stereotype.Component;

@Component
public class BadAuthorLoader {

    private final DataLoader<Long, Author> authorLoader;

    public BadAuthorLoader(AuthorService authorService) {
        this.authorLoader = DataLoaderFactory.newMappedDataLoader(
                authorIds -> authorService.findByIds(authorIds).toFuture()
        );
    }

    public DataLoader<Long, Author> getLoader() {
        return authorLoader;
    }
}
~~~

`BadAuthorLoader` là singleton component và giữ DataLoader trong field suốt vòng đời application context. Những request khác nhau cùng truy cập một queue và một cache. Dùng `static` field cho loader cũng tạo ra cùng lỗi về phạm vi, đồng thời làm dependency khó quản lý hơn.

Các rủi ro thường gặp:

1. **Rò rỉ dữ liệu giữa người dùng:** cache của request trước có thể được dùng lại cho request sau, kể cả khi người dùng sau không có quyền xem dữ liệu đó.
2. **Rò rỉ giữa tenant:** cùng một ID có thể đại diện cho bản ghi khác nhau ở tenant khác nhau, nhưng global cache chỉ dùng ID làm key.
3. **Dữ liệu cũ:** một mutation cập nhật dữ liệu nhưng cache toàn cục vẫn giữ giá trị trước đó.
4. **Queue trộn request:** các lần gọi `load` từ nhiều execution có thể đi vào cùng loader và cùng chu kỳ dispatch.
5. **Khó xác định vòng đời:** cache không tự kết thúc khi request hoàn tất, làm tăng bộ nhớ và khiến kiểm thử phụ thuộc thứ tự chạy.

DataLoader không phải một cache ứng dụng toàn cục và cũng không nên được dùng như một singleton service.

## 3. Vòng đời đúng: đăng ký toàn cục, instance theo execution

Spring for GraphQL cung cấp `BatchLoaderRegistry` để đăng ký batch loader tập trung. Registry đăng ký có thể tồn tại như bean singleton, nhưng DataLoader instances và `DataLoaderRegistry` dùng để thực thi một GraphQL operation có phạm vi riêng.

~~~mermaid
flowchart TD
    A[Spring Application Context] --> B[Singleton BatchLoaderRegistry]
    B --> C[Loader registration definitions]
    D[GraphQL Request A] --> E[DataLoaderRegistry A]
    F[GraphQL Request B] --> G[DataLoaderRegistry B]
    C --> E
    C --> G
    E --> H[DataLoader A: queue and cache]
    G --> I[DataLoader B: queue and cache]
    H --> J[Batch load for Request A]
    I --> K[Batch load for Request B]
~~~

Mỗi request/execution có queue và cache riêng. Cùng một registration definition có thể được dùng để tạo DataLoader cho nhiều execution mà không chia sẻ request state.

Phân biệt hai khái niệm:

| Thành phần | Phạm vi | Có thể dùng singleton? |
| --- | --- | --- |
| `BatchLoaderRegistry` | Application context; lưu các registration definitions | Có |
| Hàm batch loader/service không giữ state request | Application context | Có thể |
| `DataLoaderRegistry` | Một GraphQL execution | Không |
| `DataLoader<K, V>` | Một GraphQL execution | Không |
| Queue và cache bên trong DataLoader | Một GraphQL execution | Không |
| `GraphQLContext` chứa principal/tenant của request | Một GraphQL execution | Không dùng làm global mutable state |

## 4. Đăng ký loader qua BatchLoaderRegistry

Ví dụ ứng dụng có `Book` chứa `authorId`, và cần tải `Author` theo ID.

Model:

~~~java
public record Book(Long id, String title, Long authorId) {}

public record Author(Long id, String name) {}
~~~

Service cung cấp batch operation:

~~~java
import java.util.Map;
import java.util.Set;
import reactor.core.publisher.Mono;

public interface AuthorService {
    Mono<Map<Long, Author>> findByIds(Set<Long> authorIds);
    Mono<Map<Long, Author>> findByTenantAndIds(String tenantId, Set<Long> authorIds);
}
~~~

Đăng ký batch loader một lần khi application context khởi tạo:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.BatchLoaderRegistry;

@Configuration(proxyBeanMethods = false)
public class DataLoaderConfiguration {

    public DataLoaderConfiguration(
            BatchLoaderRegistry registry,
            AuthorService authorService
    ) {
        registry.forTypePair(Long.class, Author.class)
                .registerMappedBatchLoader((authorIds, environment) ->
                        authorService.findByIds(authorIds)
                );
    }
}
~~~

`BatchLoaderRegistry` giữ registration cho cặp key/value `Long` và `Author`. Khi một GraphQL execution cần loader tương ứng, Spring tạo DataLoader trong registry của execution đó. Service có thể là singleton vì nó không lưu queue/cache của DataLoader; service chỉ thực hiện truy vấn batch theo tập ID được truyền vào.

Mapped batch loader trả về map từ key sang value. Những key không xuất hiện trong map được xem là không có kết quả tương ứng; nếu field GraphQL là Non-Null, cần thiết kế cách xử lý trường hợp thiếu dữ liệu phù hợp với schema.

## 5. Inject DataLoader vào annotated controller

Spring for GraphQL có thể cung cấp DataLoader tương ứng cho tham số handler method:

~~~java
import java.util.concurrent.CompletableFuture;

import org.dataloader.DataLoader;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    @SchemaMapping(typeName = "Book", field = "author")
    public CompletableFuture<Author> author(
            Book book,
            DataLoader<Long, Author> authorLoader
    ) {
        return authorLoader.load(book.authorId());
    }
}
~~~

Controller không tạo DataLoader, không giữ DataLoader trong field và không gọi `dispatch()` thủ công. GraphQL execution quản lý việc dispatch các batch loader theo chu kỳ thực thi. Mỗi resolver chỉ yêu cầu key bằng `load`; DataLoader gom các yêu cầu phù hợp rồi trả future cho từng field.

Với một query tải nhiều quyển sách, các lần gọi `authorLoader.load(...)` có thể được gom thành một lần gọi `AuthorService.findByIds(...)`. Nếu hai sách có cùng `authorId`, cache theo request có thể loại bỏ lần tải trùng.

## 6. Dùng @BatchMapping để Spring quản lý DataLoader

Nếu không cần truy cập DataLoader trực tiếp, `@BatchMapping` là cách ngắn hơn. Spring for GraphQL tự đăng ký batch loader và DataLoader tương ứng:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.graphql.data.method.annotation.BatchMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

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

        return authorService.findByIds(authorIds)
                .map(authors -> books.stream()
                        .filter(book -> authors.containsKey(book.authorId()))
                        .collect(Collectors.toMap(
                                book -> book,
                                book -> authors.get(book.authorId())
                        )));
    }
}
~~~

Ví dụ dùng service reactive đã khai báo ở mục trước. `@BatchMapping` vẫn dùng cơ chế DataLoader do Spring quản lý; không cần tự tạo registry hoặc cache.

## 7. Không giữ request state trong singleton service

Một singleton service dùng để truy cập repository hoặc API là bình thường. Vấn đề phát sinh khi service lưu dữ liệu phụ thuộc request trong field mutable:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

import org.springframework.stereotype.Service;

@Service
public class BadAuthorService {

    private final AuthorRepository repository;
    private final Map<Long, Author> lastRequestCache = new HashMap<>();
    private String currentTenant;

    public BadAuthorService(AuthorRepository repository) {
        this.repository = repository;
    }

    public Map<Long, Author> findByIds(Set<Long> ids, String tenantId) {
        this.currentTenant = tenantId;
        Map<Long, Author> result = repository.findAuthors(ids, currentTenant);
        lastRequestCache.putAll(result);
        // Returns shared mutable state across requests.
        return lastRequestCache;
    }
}
~~~

Singleton bean có thể được nhiều GraphQL execution gọi đồng thời. `currentTenant` và `lastRequestCache` khiến dữ liệu của một request có thể ghi đè hoặc ảnh hưởng request khác.

Hãy truyền dữ liệu cần thiết qua tham số method và trả kết quả cục bộ:

~~~java
import java.util.Map;
import java.util.Set;

import org.springframework.stereotype.Service;

@Service
public class JpaAuthorLookup {

    private final AuthorRepository repository;

    public JpaAuthorLookup(AuthorRepository repository) {
        this.repository = repository;
    }

    public Map<Long, Author> findByIdsForTenant(Set<Long> ids, String tenantId) {
        return repository.findByTenantIdAndIdIn(tenantId, ids).stream()
                .collect(java.util.stream.Collectors.toMap(
                        AuthorEntity::getId,
                        this::toDomain
                ));
    }

    private Author toDomain(AuthorEntity entity) {
        return new Author(entity.getId(), entity.getName());
    }
}
~~~

Service singleton vẫn an toàn khi các dependency của nó được thiết kế để dùng đồng thời và method không ghi request state vào field dùng chung. Repository Spring Data thông thường được thiết kế để sử dụng qua bean proxy; không vì vậy mà nên lưu `EntityManager`, transaction hoặc mutable request data tùy ý trong field.

## 8. Truyền tenant và security context theo request

Batch loader đôi khi cần biết tenant, principal hoặc locale để truy vấn dữ liệu đúng phạm vi. Không đặt các giá trị này vào biến `static`, field singleton hoặc một biến `currentUser` dùng chung.

Với Spring for GraphQL, thông tin theo request có thể được đặt trong `GraphQLContext` ở giai đoạn xử lý transport/interceptor. `BatchLoaderRegistry` hỗ trợ truyền context của GraphQL execution tới batch loader thông qua `BatchLoaderEnvironment`.

Luồng xử lý nên là:

1. Xác thực request và xác định principal/tenant từ nguồn tin cậy.
2. Đưa thông tin cần thiết vào `GraphQLContext` của execution hiện tại.
3. Batch loader đọc context của execution đó khi thực hiện truy vấn batch.
4. Service luôn áp dụng tenant và quyền truy cập vào truy vấn dữ liệu.

Ví dụ về ý tưởng đọc context trong callback context-aware:

~~~java
import graphql.GraphQLContext;
import java.util.Set;
import reactor.core.publisher.Mono;

registry.forTypePair(Long.class, Author.class)
        .registerMappedBatchLoader((authorIds, environment) -> {
            GraphQLContext graphQLContext =
                    (GraphQLContext) environment.getContext();
            String tenantId = graphQLContext.get("tenantId");
            return authorService.findByTenantAndIds(tenantId, authorIds);
        });
~~~

Callback context-aware phụ thuộc overload `registerMappedBatchLoader` và kiểu context của phiên bản Spring for GraphQL/GraphQL Java đang dùng. Nếu API trả context ở dạng `Object`, cần cast hoặc chuyển đổi đúng kiểu trước khi đọc. Ý nghĩa quan trọng là context phải đến từ execution hiện tại, không phải singleton field.

Hợp đồng service cho ví dụ context-aware cần nhận tenant như tham số:

~~~java
Mono<Map<Long, Author>> findByTenantAndIds(String tenantId, Set<Long> authorIds);
~~~

Không tin `tenantId` do client tùy ý gửi trong argument nếu chưa kiểm tra quyền. Dùng principal đã xác thực để xác định tenant, sau đó kết hợp điều kiện tenant trong repository/service. DataLoader cache theo key không tự bổ sung tenant vào key; nếu cùng một execution có thể tải cùng ID dưới nhiều phạm vi khác nhau, hãy đưa phạm vi đó vào key hoặc tách loader theo đúng phạm vi.

## 9. DataLoader cache có phạm vi request

DataLoader thường bật cache theo key. Cache này giúp tránh tải lặp trong cùng một GraphQL execution:

~~~java
CompletableFuture<Author> first = authorLoader.load(100L);
CompletableFuture<Author> second = authorLoader.load(100L);
~~~

Khi caching được bật, hai lần `load(100L)` trong cùng loader có thể dùng chung kết quả future. Một execution khác có DataLoader instance khác nên không đọc cache của execution trước.

Điều này khác với cache toàn cục trong service:

| Loại cache | Vòng đời | Mục đích |
| --- | --- | --- |
| DataLoader cache | Một GraphQL execution | Khử tải lặp và chia sẻ kết quả trong cùng query |
| Cache trong singleton service | Có thể kéo dài suốt application context | Cache ứng dụng; phải tự thiết kế key, TTL, invalidation và quyền truy cập |
| Redis/Caffeine cache dùng chung | Nhiều request/instance | Cache phân tán hoặc cache ứng dụng có chủ đích |

Không dùng DataLoader cache thay cho cache nghiệp vụ lâu dài. Ngược lại, nếu ứng dụng cần cache dùng chung, hãy thiết kế nó như một thành phần riêng có key chứa đủ tenant, locale, phiên bản dữ liệu và các chiều authorization phù hợp.

## 10. Khi nào nên tắt cache của DataLoader?

Batching và caching là hai tính năng liên quan nhưng khác nhau. Có thể cần gom nhiều key thành một batch nhưng không muốn tái sử dụng kết quả theo key trong cùng execution, ví dụ khi mỗi lần load mang context riêng hoặc dữ liệu phải được đọc mới theo semantics đặc biệt.

GraphQL Java cung cấp `DataLoaderOptions` để cấu hình cache, batch size và cache key. Có thể tắt caching cho một loader bằng `setCachingEnabled(false)` trong options của registration tương ứng.

Tắt cache không làm DataLoader thành global hay request-scoped; vòng đời của instance vẫn thuộc execution hiện tại. Batching vẫn có thể hoạt động, nhưng cùng một key có thể xuất hiện nhiều lần trong batch và backend phải xử lý điều đó. Chỉ tắt cache khi yêu cầu dữ liệu đòi hỏi; mặc định request-scoped cache thường giúp tránh truy vấn trùng.

Nếu cache key mặc định không đại diện đủ dữ liệu đầu vào, hãy cân nhắc custom cache key hoặc dùng composite key thay vì tạo một DataLoader global.

## 11. Cập nhật cache sau mutation

Một GraphQL operation có thể chứa mutation cập nhật bản ghi rồi tiếp tục resolve các field phụ thuộc vào bản ghi đó. Nếu DataLoader trong cùng execution đã cache giá trị cũ, cần xóa hoặc thay thế entry tương ứng.

Ví dụ:

~~~java
@MutationMapping
public CompletableFuture<Book> renameBook(
        @Argument("id") Long id,
        @Argument("title") String title,
        DataLoader<Long, Book> bookLoader
) {
    return bookService.renameAsync(id, title)
            .thenApply(updated -> {
                bookLoader.clear(updated.id());
                bookLoader.prime(updated.id(), updated);
                return updated;
            });
}
~~~

Ví dụ giả định ứng dụng đã đăng ký DataLoader `Long` → `Book` trong `BatchLoaderRegistry` để Spring có thể inject loader vào mutation handler. `clear(key)` xóa entry cũ của key trong DataLoader hiện tại. `prime(key, value)` đưa giá trị mới vào cache nếu key chưa có. Kết hợp hai thao tác giúp field resolver chạy sau mutation nhận dữ liệu mới trong cùng execution.

Đây chỉ là invalidation cache request-scoped. Nếu ứng dụng có Redis/Caffeine cache dùng chung, mutation cũng cần cập nhật hoặc xóa cache ứng dụng theo chính sách riêng. Không giải quyết cache toàn cục bằng cách giữ DataLoader sống lâu hơn.

## 12. Chọn key và cache key an toàn

Key của DataLoader phải đại diện đầy đủ cho dữ liệu cần tải. Nếu chỉ dùng `authorId` nhưng kết quả còn phụ thuộc tenant, locale hoặc trạng thái quyền, cần xem các yếu tố đó có cố định trong một execution hay không.

Ví dụ key đơn giản:

~~~java
DataLoader<Long, Author> authorLoader;
~~~

Ví dụ composite key khi cùng một execution có nhiều locale:

~~~java
public record AuthorKey(Long authorId, String locale) {}

DataLoader<AuthorKey, Author> localizedAuthorLoader;
~~~

Với key composite, batch loader nhận tập `AuthorKey` và trả map theo chính các key đó. Nếu dùng `cacheKeyFunction`, bảo đảm hàm tạo key không loại bỏ tenant/locale hoặc thông tin làm thay đổi kết quả. Key không đầy đủ có thể khiến hai yêu cầu khác nhau dùng chung một cache entry.

Authorization vẫn phải được kiểm tra ở service/data access layer. Một cache hit không phải bằng chứng người dùng hiện tại có quyền xem dữ liệu.

## 13. Kiểm thử không rò rỉ state giữa các request

Nên kiểm thử ít nhất hai đặc tính:

- Trong một GraphQL execution, các lần load cùng key có thể được gộp/cache theo cấu hình.
- Giữa hai execution riêng biệt, cùng key phải đi qua DataLoader instance và cache riêng.

Ví dụ kiểm thử tích hợp: gửi hai GraphQL request độc lập có cùng `bookId` hoặc `authorId`, sau đó xác nhận batch service được gọi cho từng execution. Có thể dùng `@MockitoBean` hoặc bộ đếm trong fake service để quan sát số lần gọi.

Các ca kiểm thử quan trọng:

1. Một query tải nhiều parent object và xác nhận batch service nhận nhiều key trong một lần gọi.
2. Hai field trong cùng execution yêu cầu cùng key và xác nhận caching hoạt động như mong muốn.
3. Hai request khác nhau cùng yêu cầu một key nhưng batch service được gọi riêng cho từng request.
4. Hai tenant khác nhau cùng yêu cầu ID giống nhau nhưng kết quả luôn thuộc tenant tương ứng.
5. Mutation cập nhật bản ghi và DataLoader được `clear`/`prime` trước khi field phụ thuộc đọc lại.
6. Khi tắt caching, batching vẫn hoạt động và backend xử lý key trùng đúng cách.
7. Batch loader không giữ danh sách key, principal hoặc kết quả của request sau khi execution kết thúc.

Đối với test tenant/security, nên thiết lập context khác nhau cho hai request bằng interceptor hoặc test transport phù hợp, không thay đổi một biến singleton `currentTenant` giữa hai lần gọi.

## 14. Những anti-pattern cần tránh

| Anti-pattern | Vì sao nguy hiểm | Cách làm đúng |
| --- | --- | --- |
| `static DataLoader<K,V>` | Chia sẻ queue và cache giữa executions | Inject DataLoader vào handler từ registry theo execution |
| Singleton giữ `DataLoaderRegistry` | Registry và loader instances không còn cô lập theo request | Dùng `BatchLoaderRegistry` để lưu registration definitions |
| Singleton service có field `currentTenant` | Request đồng thời có thể ghi đè context của nhau | Truyền tenant qua tham số/context của execution |
| Static `Map<K,V>` làm cache mặc định | Không có TTL, invalidation và scope authorization rõ ràng | Dùng DataLoader cache theo request hoặc cache ứng dụng được thiết kế riêng |
| Batch loader giữ mutable list keys | Key của request trước có thể tồn tại khi request khác chạy | Xử lý keys như input cục bộ của callback, không lưu vào field |
| Gọi `dispatch()` thủ công trong resolver | Can thiệp chu kỳ dispatch do GraphQL quản lý | Chỉ gọi `load(key)` và để GraphQL execution dispatch |
| Dùng key chỉ có ID trong nhiều phạm vi dữ liệu | Có thể trả nhầm tenant/locale hoặc phiên bản dữ liệu | Dùng composite key hoặc loader riêng theo phạm vi |
| Dùng cache hit thay cho authorization | Có thể trả dữ liệu mà người dùng hiện tại không được phép xem | Kiểm tra quyền ở service cho mọi đường truy cập phù hợp |

## 15. Quy trình triển khai DataLoader an toàn

Khi cần giảm N+1 bằng DataLoader trong Spring for GraphQL:

1. Xác định field liên kết và key cần tải theo batch.
2. Ưu tiên `@BatchMapping` nếu logic batch gắn trực tiếp với source field.
3. Dùng `BatchLoaderRegistry` nếu cần tái sử dụng loader hoặc inject `DataLoader<K,V>` vào nhiều resolver.
4. Đăng ký batch loader trong application configuration; không tạo DataLoader instance trong field singleton.
5. Để Spring tạo DataLoaderRegistry và DataLoader instance riêng cho từng GraphQL execution.
6. Truyền principal, tenant và locale qua `GraphQLContext`/context-aware batch loader; không dùng global mutable state.
7. Bảo đảm key/cache key chứa đủ thông tin ảnh hưởng kết quả.
8. Giữ cache DataLoader trong phạm vi execution; thiết kế cache dùng chung thành thành phần riêng nếu thật sự cần.
9. Sau mutation, clear/prime loader của execution và invalidation cache ứng dụng nếu có.
10. Kiểm thử batching, cache hit trong một execution và cô lập giữa hai request độc lập.

DataLoader chỉ phát huy đúng tác dụng khi queue và cache của nó thuộc đúng GraphQL execution. Trong Spring for GraphQL, `BatchLoaderRegistry` và `@BatchMapping` giúp giữ registration dùng chung nhưng tạo loader state riêng cho từng lần thực thi. Cách tổ chức này giảm N+1 mà vẫn giữ ranh giới dữ liệu giữa người dùng và request.

## Tài liệu tham khảo

- [Spring for GraphQL — Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html#execution.batch-loading)
- [Spring for GraphQL — BatchLoaderRegistry API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/execution/BatchLoaderRegistry.html)
- [Spring for GraphQL — BatchMapping API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/method/annotation/BatchMapping.html)
- [GraphQL Java — DataLoader](https://github.com/graphql-java/java-dataloader)
