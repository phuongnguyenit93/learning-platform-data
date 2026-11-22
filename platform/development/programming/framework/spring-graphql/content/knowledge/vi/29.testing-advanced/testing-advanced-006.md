# Test DataLoader trong Spring for GraphQL

DataLoader giúp gom nhiều lần tải dữ liệu thành một batch và cache kết quả trong phạm vi một GraphQL execution. Khi kiểm thử, cần xác nhận cả hai hành vi: nhiều field cùng yêu cầu dữ liệu được gom lại để giảm N+1, và cache của một execution không bị dùng chung cho request khác.

Spring for GraphQL tích hợp DataLoader qua `BatchLoaderRegistry` và `@BatchMapping`. `GraphQlTester` cho phép kiểm tra hành vi này ở mức GraphQL operation: gửi một query có nhiều parent object, assert dữ liệu con, rồi xác minh batch service được gọi đúng số lần với tập key mong đợi. Có thể kết hợp unit test trực tiếp GraphQL Java DataLoader để kiểm tra cache, dispatch và batch loader độc lập với Spring.

## 1. Những gì cần kiểm thử

Giả sử query trả về nhiều quyển sách, mỗi quyển cần thêm thông tin tác giả. Nếu resolver gọi repository riêng cho từng sách, ứng dụng có thể gặp N+1 query. DataLoader gom các key lại và gọi batch loader.

Các hành vi quan trọng cần xác minh:

| Hành vi | Điều cần assert |
| --- | --- |
| Batching | Nhiều key được xử lý trong một lần gọi batch loader khi cùng nằm trong một dispatch batch |
| Cache trong execution | Cùng key được load nhiều lần chỉ cần một kết quả theo cache policy mặc định |
| Request isolation | Hai GraphQL execution độc lập có DataLoader/cache riêng |
| Kết quả ánh xạ | Mỗi parent nhận đúng object con theo key của nó |
| Missing key | Key không có trong mapped result được xử lý theo nullability và contract của schema |
| Batch error | Lỗi từ batch loader trở thành GraphQL error có path phù hợp |
| Context | Tenant/principal/locale của execution được truyền đúng tới batch loader |
| Invalidation | Mutation xóa hoặc cập nhật cache entry trong execution khi cần |

Không nên chỉ assert rằng query trả về đúng JSON. Một resolver không dùng DataLoader vẫn có thể trả cùng dữ liệu nhưng phát sinh một truy vấn cho mỗi parent. Cần kiểm tra số lần gọi service/repository hoặc số batch và các key thực tế.

## 2. Thiết kế ví dụ Book và Author

Schema có query trả về danh sách sách và field con `author`:

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

Model Java:

~~~java
public record Book(String id, String title, Long authorId) {}

public record Author(Long id, String name) {}
~~~

`Book.authorId` là khóa liên kết tới tác giả. Field `Book.author` được resolve riêng bằng DataLoader, còn root query chỉ tải danh sách sách.

Service contract:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;

import reactor.core.publisher.Mono;

public interface BookService {
    List<Book> findAll();
}

public interface AuthorService {
    Mono<Map<Long, Author>> findByIds(Set<Long> authorIds);
}
~~~

Mapped batch loader nhận một tập author ID và trả về map từ ID đến Author. Dùng `Set` giúp thể hiện rõ key được gom và loại trùng trong một batch.

## 3. Đăng ký DataLoader qua BatchLoaderRegistry

Đăng ký batch loader một lần trong application configuration:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.BatchLoaderRegistry;

@Configuration(proxyBeanMethods = false)
public class AuthorDataLoaderConfiguration {

    public AuthorDataLoaderConfiguration(
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

`BatchLoaderRegistry` giữ registration definition. Spring dùng registration đó để tạo `DataLoaderRegistry` và DataLoader instances cho từng GraphQL execution. Vì vậy, cấu hình đăng ký có thể là singleton bean, còn DataLoader và cache của nó có scope theo execution.

## 4. Inject DataLoader vào resolver

Root controller tải danh sách sách:

~~~java
import java.util.List;

import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> books() {
        return bookService.findAll();
    }
}
~~~

Resolver field `author` sử dụng DataLoader được Spring cung cấp:

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

Resolver chỉ gọi `load(key)` và trả về future. Không tự gọi `dispatch()` trong controller; GraphQL Java quản lý dispatch trong execution. Điều này quan trọng khi test: hãy thực thi GraphQL operation thật để quan sát batching, thay vì tự dispatch loader trong resolver.

Batching còn phụ thuộc vào execution strategy. GraphQL Java dùng `AsyncExecutionStrategy` để theo dõi các field đang được resolve và chọn thời điểm dispatch batch. Spring for GraphQL dùng async execution strategy mặc định. Nếu ứng dụng thay thế execution strategy, hãy kiểm tra rằng strategy mới vẫn hỗ trợ DataLoader batching; một số strategy dựa trên executor có thể dispatch từng field riêng và làm mất lợi ích gom batch. Integration test kiểm tra số lần gọi batch service giúp phát hiện thay đổi này.

## 5. Kiểm thử batching bằng @GraphQlTest và GraphQlTester

`@GraphQlTest` tạo test slice cho GraphQL controllers. Dùng `@MockitoBean` để thay các service bằng mock, sau đó kiểm tra response và số lần gọi batch service.

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.context.annotation.Import;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import reactor.core.publisher.Mono;

import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;

@GraphQlTest({BookQueryController.class, BookController.class})
@Import(AuthorDataLoaderConfiguration.class)
class DataLoaderBatchingTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @MockitoBean
    AuthorService authorService;

    @Test
    void batchesAuthorLoadsForAllBooks() {
        given(bookService.findAll()).willReturn(List.of(
                new Book("book-1", "GraphQL Basics", 10L),
                new Book("book-2", "Spring GraphQL", 10L),
                new Book("book-3", "DataLoader in Practice", 20L)
        ));

        given(authorService.findByIds(Set.of(10L, 20L)))
                .willReturn(Mono.just(Map.of(
                        10L, new Author(10L, "Ada"),
                        20L, new Author(20L, "Grace")
                )));

        graphQlTester.document("""
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
                """)
                .execute()
                .path("books[*].author.name")
                .entityList(String.class)
                .containsExactly("Ada", "Ada", "Grace");

        verify(authorService).findByIds(Set.of(10L, 20L));
    }
}
~~~

Test này xác minh ba điều:

1. GraphQL trả đúng tác giả cho từng quyển sách.
2. Hai quyển sách có cùng `authorId` không khiến backend phải tải cùng tác giả hai lần trong batch.
3. `AuthorService.findByIds` chỉ được gọi một lần với tập key `{10, 20}`.

Nếu resolver gọi `authorService.findById(...)` trực tiếp cho từng sách, assertion số lần gọi sẽ thất bại dù response data có thể vẫn đúng. Đây là lý do cần kiểm tra cả kết quả lẫn tương tác với batch service.

`@MockitoBean` có trong các phiên bản Spring Boot mới. Với phiên bản cũ hơn, dùng cơ chế mock bean tương ứng của phiên bản đó, chẳng hạn `@MockBean`. Đảm bảo test slice nạp schema SDL, `BatchLoaderRegistry` và configuration đăng ký loader.

## 6. Kiểm tra cache khi cùng key được load nhiều lần

Trong ví dụ trên, hai quyển sách cùng yêu cầu author ID `10`. Resolver gọi `authorLoader.load(10L)` hai lần. Với cache mặc định được bật, DataLoader dùng chung future cho cùng key trong một execution và mapped batch loader chỉ nhận key duy nhất một lần.

Để làm rõ semantics cache của GraphQL Java, có thể viết unit test cho DataLoader trực tiếp:

~~~java
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;

import org.dataloader.DataLoader;
import org.dataloader.DataLoaderFactory;
import org.dataloader.MappedBatchLoader;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class DataLoaderUnitTests {

    @Test
    void batchesKeysAndCachesDuplicateLoads() {
        AtomicInteger batchCalls = new AtomicInteger();

        MappedBatchLoader<Long, String> batchLoader = keys -> {
            batchCalls.incrementAndGet();
            return CompletableFuture.completedFuture(Map.of(
                    1L, "Ada",
                    2L, "Grace"
            ));
        };

        DataLoader<Long, String> dataLoader =
                DataLoaderFactory.newMappedDataLoader(batchLoader);

        CompletableFuture<String> first = dataLoader.load(1L);
        CompletableFuture<String> duplicate = dataLoader.load(1L);
        CompletableFuture<String> second = dataLoader.load(2L);

        dataLoader.dispatchAndJoin();

        assertThat(first.join()).isEqualTo("Ada");
        assertThat(duplicate.join()).isEqualTo("Ada");
        assertThat(second.join()).isEqualTo("Grace");
        assertThat(batchCalls).hasValue(1);
    }
}
~~~

Ở unit test thuần, gọi `dispatchAndJoin()` để kích hoạt batch vì không có GraphQL execution quản lý dispatch. Trong resolver thực tế, không gọi method này; GraphQL Java dispatch DataLoader tự động.

Test trên kiểm tra hai lần `load(1L)` và một lần `load(2L)` được xử lý trong một batch. Nếu tắt cache, hai lần load cùng key có thể được đưa vào batch nhiều lần tùy loader/options. Hãy viết test theo cache policy mà ứng dụng chủ đích cấu hình.

## 7. Kiểm tra DataLoader được tạo riêng cho mỗi request

DataLoader cache chỉ có phạm vi một GraphQL execution. Dùng cùng một `GraphQlTester` để thực thi hai operation riêng biệt, rồi xác minh batch service được gọi hai lần:

~~~java
@Test
void doesNotShareDataLoaderCacheAcrossExecutions() {
    given(bookService.findAll()).willReturn(List.of(
            new Book("book-1", "GraphQL Basics", 10L)
    ));
    given(authorService.findByIds(Set.of(10L)))
            .willReturn(Mono.just(Map.of(10L, new Author(10L, "Ada"))));

    String document = "{ books { id author { name } } }";

    graphQlTester.document(document)
            .execute()
            .path("books[0].author.name")
            .entity(String.class)
            .isEqualTo("Ada");

    graphQlTester.document(document)
            .execute()
            .path("books[0].author.name")
            .entity(String.class)
            .isEqualTo("Ada");

    verify(authorService, org.mockito.Mockito.times(2))
            .findByIds(Set.of(10L));
}
~~~

Hai lần `execute()` là hai GraphQL executions riêng biệt. Mỗi lần có `DataLoaderRegistry` và DataLoader cache mới, vì vậy cùng author ID vẫn được batch service tải lại. Spring không giữ cache DataLoader qua các request chỉ vì `GraphQlTester` hoặc `BatchLoaderRegistry` được tái sử dụng.

Nếu test chỉ gọi `load(key)` hai lần trong cùng execution, kết quả có thể được cache. Nếu gửi hai GraphQL request độc lập, không nên mong cache của request đầu được dùng lại cho request sau.

## 8. Kiểm thử @BatchMapping

`@BatchMapping` là cách khai báo batch resolver ngắn gọn. Spring for GraphQL tự đăng ký DataLoader cho source field. Test có thể dùng cùng chiến lược: tạo nhiều parent object, assert child data và verify service được gọi theo batch.

Ví dụ resolver:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.graphql.data.method.annotation.BatchMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class BookBatchController {

    private final AuthorService authorService;

    public BookBatchController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Mono<Map<Book, Author>> author(List<Book> books) {
        Set<Long> authorIds = books.stream()
                .map(Book::authorId)
                .collect(Collectors.toSet());

        return authorService.findByIds(authorIds)
                .map(authorsById -> books.stream()
                        .filter(book -> authorsById.containsKey(book.authorId()))
                        .collect(Collectors.toMap(
                                book -> book,
                                book -> authorsById.get(book.authorId())
                        )));
    }
}
~~~

Với `@BatchMapping`, batch loader nhận danh sách source object (`Book`) và trả map từ source object đến kết quả (`Author`). Trong ví dụ, service vẫn truy vấn theo tập author ID đã loại trùng. Khi test, kiểm tra `findByIds` được gọi một lần với tập ID mong đợi.

Nếu dùng record `Book`, `equals` và `hashCode` được sinh theo các thành phần record, phù hợp làm key trong map ví dụ. Với entity mutable, cần bảo đảm equality/hash code ổn định trong thời gian dùng làm map key.

## 9. Kiểm tra thứ tự và mapping kết quả

Batch loader có thể trả kết quả theo thứ tự khác với thứ tự key đầu vào. Với mapped batch loader, DataLoader ghép kết quả dựa trên key trong map, không dựa vào thứ tự iteration của map.

Test nên cố ý trả map có thứ tự khác thứ tự sách và vẫn assert mỗi sách nhận đúng tác giả:

~~~java
given(authorService.findByIds(Set.of(10L, 20L)))
        .willReturn(Mono.just(Map.of(
                20L, new Author(20L, "Grace"),
                10L, new Author(10L, "Ada")
        )));

graphQlTester.document("{ books { id author { id name } } }")
        .execute()
        .path("books[*].author.name")
        .entityList(String.class)
        .containsExactly("Ada", "Ada", "Grace");
~~~

Đây là kiểm tra quan trọng khi backend trả dữ liệu từ SQL `IN (...)`, vì database không bảo đảm thứ tự hàng nếu query không có `ORDER BY`. Nếu dùng `BatchLoader` dạng positional list thay vì mapped loader, batch function phải trả list kết quả đúng thứ tự tương ứng với list key đầu vào.

## 10. Kiểm thử missing key và nullability

Mapped batch loader có thể không trả một key trong map. DataLoader sẽ không tìm thấy value tương ứng cho key đó, và resolver có thể nhận `null` cho field.

Ví dụ service chỉ tìm được author ID `10`, còn ID `20` không tồn tại:

~~~java
given(authorService.findByIds(Set.of(10L, 20L)))
        .willReturn(Mono.just(Map.of(
                10L, new Author(10L, "Ada")
        )));
~~~

Vì SDL khai báo `author: Author` nullable, test có thể assert field thiếu dữ liệu là null trong khi các field khác vẫn có giá trị:

~~~java
graphQlTester.document("{ books { id title author { name } } }")
        .execute()
        .path("books[1].author")
        .valueIsNull();
~~~

Nếu schema đổi thành `author: Author!`, null không hợp lệ và GraphQL áp dụng null propagation lên parent. Test cần xác nhận đúng vị trí `data` bị null và error behavior nếu batch loader ném exception. Missing key trả null và batch loader phát sinh exception là hai tình huống khác nhau; không gộp chúng thành cùng một assertion.

## 11. Kiểm thử lỗi từ batch loader

Khi batch service thất bại, publisher có thể phát error:

~~~java
given(authorService.findByIds(Set.of(10L, 20L)))
        .willReturn(Mono.error(new IllegalStateException("database unavailable")));
~~~

GraphQL sẽ ghi nhận lỗi ở field hoặc các field phụ thuộc vào batch, tùy cách DataLoader phát lỗi và schema nullability. Dùng `GraphQlTester.errors()` để xác nhận error code/path, rồi assert phần data còn hợp lệ:

~~~java
graphQlTester.document("{ books { id title author { name } } }")
        .execute()
        .errors()
        .expect(error -> error.getPath() != null)
        .verify()
        .path("books[*].title")
        .entityList(String.class)
        .containsExactly("GraphQL Basics", "Spring GraphQL");
~~~

Không nên chỉ kiểm tra số lượng error. Nên assert path hoặc `extensions.code` cụ thể để bảo đảm lỗi được gắn đúng field và không bị nhầm với lỗi resolver khác.

## 12. Kiểm thử maxBatchSize và nhiều dispatch batch

DataLoader có thể giới hạn số key trong một batch bằng `maxBatchSize`. Khi số key vượt giới hạn, một lần GraphQL execution có thể tạo nhiều lần gọi batch loader.

Ví dụ cấu hình options trên registration:

~~~java
registry.forTypePair(Long.class, Author.class)
        .withOptions(options -> options.setMaxBatchSize(2))
        .registerMappedBatchLoader((authorIds, environment) ->
                authorService.findByIds(authorIds)
        );
~~~

Khi test với 5 author ID khác nhau và `maxBatchSize = 2`, kỳ vọng batch loader được gọi nhiều lần, mỗi batch không vượt quá 2 key. Số lần gọi sẽ phụ thuộc cách GraphQL Java chia batch và số key thực tế được load; với 5 key, có thể kỳ vọng 3 batch.

Có thể capture từng set key bằng Mockito `ArgumentCaptor<Set<Long>>` rồi kiểm tra:

- Tổng số key duy nhất bằng 5.
- Không batch nào có quá 2 key.
- Hợp của các batch key bằng tập ID mong đợi.
- Không có ID bị mất hoặc xử lý hai lần ngoài chính sách cache.

Giới hạn batch giúp bảo vệ database và dịch vụ downstream khỏi một truy vấn quá lớn. Test nên phản ánh giới hạn cấu hình thật của ứng dụng, không chỉ giả định mọi key luôn nằm trong một batch duy nhất.

## 13. Kiểm thử cache policy

DataLoader mặc định cache theo key trong phạm vi instance. Ứng dụng có thể tắt cache hoặc cung cấp cache key/options tùy trường hợp.

Khi tắt cache, mỗi lần `load(key)` tạo một promise riêng và batch loader dạng positional có thể nhận key trùng lặp. Tuy nhiên, `MappedBatchLoader` nhận `Set<K>`, nên bản thân contract này không biểu diễn được key trùng trong danh sách batch. Nếu cần kiểm tra chính xác duplicate keys khi tắt cache, dùng `BatchLoader<K,V>` nhận `List<K>`.

Ví dụ unit test positional batch loader không bật cache:

~~~java
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CopyOnWriteArrayList;

import org.dataloader.BatchLoader;
import org.dataloader.DataLoader;
import org.dataloader.DataLoaderFactory;
import org.dataloader.DataLoaderOptions;

import static org.assertj.core.api.Assertions.assertThat;

List<Long> receivedKeys = new CopyOnWriteArrayList<>();
BatchLoader<Long, String> batchLoader = keys -> {
    receivedKeys.addAll(keys);
    Map<Long, String> values = Map.of(1L, "Ada", 2L, "Grace");
    return CompletableFuture.completedFuture(
            keys.stream().map(values::get).toList()
    );
};

DataLoaderOptions options = DataLoaderOptions.newOptions()
        .setCachingEnabled(false)
        .build();

DataLoader<Long, String> dataLoader =
        DataLoaderFactory.newDataLoader(batchLoader, options);

var first = dataLoader.load(1L);
var duplicate = dataLoader.load(1L);
dataLoader.dispatchAndJoin();

assertThat(first.join()).isEqualTo("Ada");
assertThat(duplicate.join()).isEqualTo("Ada");
assertThat(receivedKeys).containsExactly(1L, 1L);
~~~

Test này chứng minh hai lần load cùng key được giữ thành hai phần tử trong batch positional khi cache tắt. Nếu dùng `MappedBatchLoader`, đầu vào là `Set<K>` và duplicate keys đã được loại khỏi biểu diễn batch; khi đó hãy assert số lần gọi/future và kết quả map theo contract của mapped loader.

Khi dùng custom cache key, test cũng phải chứng minh các key khác nhau không vô tình trùng cache entry.

Không nên tắt cache chỉ để làm test dễ đoán. Cache request-scoped thường hữu ích để khử tải lặp; chỉ thay đổi policy khi có yêu cầu dữ liệu cụ thể.

## 14. Kiểm thử context và tenant trong batch loader

Batch loader có thể cần tenant, principal hoặc locale của GraphQL execution. Spring for GraphQL truyền execution context qua `BatchLoaderEnvironment`, nên test phải xác nhận batch loader nhận đúng context cho request hiện tại.

Một chiến lược test:

1. Dùng `WebGraphQlTester` hoặc `HttpGraphQlTester` với interceptor xác thực/đưa tenant vào `GraphQLContext`.
2. Gửi request của tenant A và tenant B với cùng một entity ID.
3. Xác minh batch service nhận tenant tương ứng và trả dữ liệu đúng tenant.
4. Xác minh không có cache dùng chung giữa hai execution.

Không dùng một field `currentTenant` trên singleton service trong test. Hãy capture tham số tenant truyền vào service hoặc đọc context từ `BatchLoaderEnvironment` trong batch loader. Điều này giúp phát hiện lỗi rò rỉ tenant do global mutable state.

## 15. Kiểm thử cache invalidation sau mutation

Nếu mutation cập nhật một entity rồi các field con trong cùng execution tiếp tục dùng DataLoader, cache entry cũ có thể cần được xóa hoặc thay thế.

Ví dụ mutation nhận DataLoader và cập nhật cache:

~~~java
@MutationMapping
public CompletableFuture<Author> renameAuthor(
        @Argument("id") Long id,
        @Argument("name") String name,
        DataLoader<Long, Author> authorLoader
) {
    return authorService.rename(id, name)
            .doOnNext(updated -> {
                authorLoader.clear(updated.id());
                authorLoader.prime(updated.id(), updated);
            })
            .toFuture();
}
~~~

Test nên xác minh resolver sau mutation đọc được giá trị mới. `clear(key)` loại entry cũ; `prime(key, value)` thêm giá trị mới nếu key chưa có. Đây là cache của DataLoader thuộc execution hiện tại, không phải cache ứng dụng dùng chung.

Nếu ứng dụng có cache Redis/Caffeine riêng, test invalidation cache đó ở service/integration layer tương ứng. Không dùng DataLoader sống lâu hơn request để giải quyết cache nghiệp vụ.

## 16. Phân biệt test DataLoader và test repository

`GraphQlTester` phù hợp để xác minh GraphQL operation thực sự gom field load và trả dữ liệu đúng. Nó không nhất thiết phải kiểm tra SQL được sinh ra. Có thể chia test theo lớp:

| Loại test | Điều cần kiểm tra |
| --- | --- |
| Unit test DataLoader | Cache, dispatch, mapped result và batch loader thuần |
| GraphQL slice test | Resolver dùng DataLoader, batching xảy ra và response đúng |
| Service/repository test | Một batch request thực hiện query dữ liệu hiệu quả và đúng transaction |
| Integration test | Toàn bộ GraphQL stack, database, transaction và transport hoạt động cùng nhau |
| Performance test | Số query, batch size, latency và throughput dưới tải đại diện |

Không dùng một GraphQL slice test để kết luận database chỉ chạy đúng một SQL statement nếu service có thể thực hiện nhiều truy vấn bên trong. Nếu cần xác minh SQL/query count, thêm kiểm thử ở repository hoặc integration layer với công cụ đo phù hợp.

## 17. Những anti-pattern trong test DataLoader

| Anti-pattern | Vấn đề | Cách làm tốt hơn |
| --- | --- | --- |
| Chỉ assert response data | Resolver N+1 vẫn có thể trả đúng kết quả | Verify số lần gọi batch service và tập key |
| Gọi `dispatch()` trong controller | Can thiệp lifecycle do GraphQL quản lý | Chỉ gọi `load(key)` trong resolver |
| Dùng DataLoader singleton trong test | Che giấu lỗi request isolation | Đăng ký qua `BatchLoaderRegistry` và để Spring tạo loader theo execution |
| Reuse cùng cache giữa hai test request | Kết quả test phụ thuộc thứ tự hoặc dữ liệu cũ | Thực thi hai operation riêng và verify batch loader chạy riêng |
| Chỉ test một parent object | Không thể chứng minh batching | Dùng nhiều parent có key trùng và key khác nhau |
| Không kiểm tra thứ tự/mapping | Batch loader có thể trả nhầm object cho key | Assert field con của từng parent, kể cả khi map trả thứ tự khác |
| Bỏ qua missing key | Nullability có thể làm hỏng cả parent/list | Test mapped result thiếu key với schema nullable và Non-Null |
| Retry batch error vô điều kiện | Có thể lặp side effect hoặc làm tăng tải downstream | Phân loại lỗi và retry theo policy có giới hạn |

## 18. Quy trình viết test DataLoader

Khi thêm hoặc sửa DataLoader:

1. Tạo GraphQL query có nhiều parent object cần cùng một loại dữ liệu liên kết.
2. Đăng ký batch loader bằng `BatchLoaderRegistry` hoặc dùng `@BatchMapping`.
3. Dùng `GraphQlTester` để thực thi query qua GraphQL execution thật.
4. Assert dữ liệu con cho từng parent bằng `entityList` hoặc nested path.
5. Verify batch service được gọi đúng số lần và nhận đúng tập key.
6. Tạo parent có key trùng để kiểm tra cache trong cùng execution.
7. Thực thi hai request riêng để xác nhận cache không bị chia sẻ.
8. Kiểm tra missing key, lỗi batch và null propagation.
9. Nếu có `maxBatchSize`, capture các batch và kiểm tra giới hạn.
10. Nếu loader phụ thuộc tenant/principal, test context isolation.
11. Nếu mutation thay đổi dữ liệu, kiểm tra `clear`/`prime` và cache invalidation.
12. Dùng repository/performance test riêng khi cần xác nhận SQL count hoặc latency.

Một test DataLoader tốt phải chứng minh được cả kết quả GraphQL lẫn cách dữ liệu được tải. `GraphQlTester` kiểm tra hành vi từ góc nhìn operation; Mockito hoặc spy xác nhận batch invocation; unit test GraphQL Java DataLoader kiểm tra cache và dispatch. Kết hợp các lớp này giúp phát hiện N+1, cache sai phạm vi và lỗi mapping trước khi chúng xuất hiện trong môi trường thực tế.

## Tài liệu tham khảo

- [Spring for GraphQL — Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html#execution.batch-loading)
- [Spring for GraphQL — BatchLoaderRegistry API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/execution/BatchLoaderRegistry.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [GraphQL Java — DataLoader](https://github.com/graphql-java/java-dataloader)
