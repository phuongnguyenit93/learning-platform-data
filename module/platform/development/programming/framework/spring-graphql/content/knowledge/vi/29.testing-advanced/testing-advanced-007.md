# Test batch mapping trong Spring for GraphQL

`@BatchMapping` giúp Spring for GraphQL gom việc phân giải một field lồng nhau cho nhiều parent object thành một lần batch load. Khi kiểm thử, cần xác minh kết quả GraphQL đúng, batch method nhận đúng tập parent object và service/repository được gọi theo nhóm thay vì gọi riêng cho từng parent. Nếu dùng `BatchLoaderRegistry` và `DataLoader` trực tiếp, có thể kiểm thử riêng loader bằng cách đăng ký nó vào `DataLoaderRegistry`, đưa nhiều key vào hàng đợi rồi dispatch.

Spring for GraphQL cung cấp hai lớp kiểm thử bổ trợ nhau: dùng `GraphQlTester` để chạy operation qua GraphQL execution và kiểm tra mapping thực tế; dùng `DataLoaderRegistry` để kiểm tra batch loader riêng lẻ. Không nên chỉ gọi trực tiếp method Java có `@BatchMapping` rồi kết luận GraphQL đã gom batch đúng, vì cách gọi đó bỏ qua việc framework đăng ký data fetcher và điều phối DataLoader.

## 1. Vì sao cần kiểm thử batch mapping?

Giả sử query trả về nhiều sách, mỗi sách có một tác giả:

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

Nếu `Book.author` được phân giải bằng một `@SchemaMapping` thông thường và mỗi lần gọi đều truy vấn database, một query có 50 sách có thể tạo ra:

- 1 lần tải danh sách sách.
- 50 lần tải tác giả, mỗi lần cho một sách.

Đó là vấn đề N+1. `@BatchMapping` cho phép gom các parent `Book` trong cùng một batch và tải tác giả theo tập ID:

```text
GraphQL query
     |
     v
Load 50 books
     |
     v
Collect parent Book objects
     |
     v
@BatchMapping(author)
     |
     v
Load authors for unique author IDs
     |
     v
Map each Book to its Author
```

Test cần xác minh cả dữ liệu lẫn hành vi gom batch. Chỉ kiểm tra danh sách `author.name` chưa đủ để phát hiện một implementation vẫn gọi repository 50 lần nhưng tình cờ trả đúng dữ liệu.

## 2. Chuẩn bị schema và model cho ví dụ

Schema SDL:

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

Đặt file schema ở `src/main/resources/graphql/books.graphqls` hoặc trong schema location mà ứng dụng đã cấu hình.

Java model dùng record:

```java
public record Book(String id, String title, String authorId) {}

public record Author(String id, String name) {}
```

Record có `equals` và `hashCode` dựa trên các thành phần của record, nên có thể dùng `Book` làm key trong `Map<Book, Author>` của ví dụ. Nếu dùng entity mutable hoặc class thông thường, hãy bảo đảm key có equality/hash semantics ổn định trong suốt quá trình batch mapping.

Để dùng `GraphQlTester`, thêm dependency kiểm thử:

```groovy
dependencies {
    testImplementation 'org.springframework.graphql:spring-graphql-test'
}
```

Nếu dự án dùng Spring Boot, để dependency management của Boot quản lý version tương thích với Spring GraphQL.

Các service được controller sử dụng:

```java
public interface BookCatalog {
    List<Book> findAll();
}

public interface AuthorCatalog {
    Map<String, Author> findAllById(Set<String> authorIds);
}
```

`AuthorCatalog.findAllById` nhận một tập ID và trả map theo ID để batch method có thể ghép tác giả về đúng sách.

## 3. Viết controller với `@BatchMapping`

Controller:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.graphql.data.method.annotation.BatchMapping;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
class BookController {

    private final BookCatalog bookCatalog;
    private final AuthorCatalog authorCatalog;

    BookController(BookCatalog bookCatalog, AuthorCatalog authorCatalog) {
        this.bookCatalog = bookCatalog;
        this.authorCatalog = authorCatalog;
    }

    @QueryMapping
    List<Book> books() {
        return bookCatalog.findAll();
    }

    @BatchMapping(typeName = "Book", field = "author")
    Map<Book, Author> author(List<Book> books) {
        Set<String> authorIds = books.stream()
            .map(Book::authorId)
            .collect(Collectors.toSet());

        Map<String, Author> authors = authorCatalog.findAllById(authorIds);
        Map<Book, Author> result = new LinkedHashMap<>();

        for (Book book : books) {
            Author author = authors.get(book.authorId());
            if (author != null) {
                result.put(book, author);
            }
        }

        return result;
    }
}
```

`@BatchMapping` tạo batch data fetcher cho field `Book.author`. Framework gom các parent `Book` được yêu cầu trong cùng batch rồi truyền vào tham số `List<Book>`.

`Map<Book, Author>` ánh xạ từng parent sang giá trị field tương ứng. Nếu một key không có trong map, field đó được phân giải thành `null`; vì vậy SDL khai báo `author: Author` nullable trong ví dụ. Nếu schema khai báo `author: Author!`, test cần bảo đảm mọi sách đều có tác giả hoặc kiểm tra lỗi Non-null propagation theo chủ ý.

Nếu tên method trùng tên field, có thể bỏ `field = "author"`. Nếu controller chỉ có một mapping cho một type và method name là `author`, annotation có thể viết ngắn hơn:

```java
@BatchMapping
Map<Book, Author> author(List<Book> books) {
    // batch loading
}
```

Khai báo rõ `typeName` và `field` thường giúp ví dụ dễ đọc hơn và tránh phụ thuộc vào suy luận tên.

## 4. Kiểm thử `@BatchMapping` bằng `@GraphQlTest` và `GraphQlTester`

`@GraphQlTest` tạo test slice cho controller GraphQL mà không cần khởi động HTTP server. `GraphQlTester` được cấu hình để gửi operation trực tiếp vào GraphQL execution. Service phụ thuộc vào controller có thể được thay bằng mock.

Ví dụ test đầy đủ:

```java
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;
import static org.mockito.Mockito.times;

@GraphQlTest(BookController.class)
class BookBatchMappingTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookCatalog bookCatalog;

    @MockitoBean
    AuthorCatalog authorCatalog;

    @Test
    void loadsAuthorsInOneBatchForAllBooks() {
        Book book1 = new Book("book-1", "GraphQL Basics", "author-1");
        Book book2 = new Book("book-2", "Spring Guide", "author-2");
        Book book3 = new Book("book-3", "GraphQL Advanced", "author-1");

        given(bookCatalog.findAll()).willReturn(List.of(book1, book2, book3));
        given(authorCatalog.findAllById(Set.of("author-1", "author-2")))
            .willReturn(Map.of(
                "author-1", new Author("author-1", "Ada"),
                "author-2", new Author("author-2", "Grace")
            ));

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
            .containsExactly("Ada", "Grace", "Ada");

        then(bookCatalog).should(times(1)).findAll();
        then(authorCatalog).should(times(1))
            .findAllById(Set.of("author-1", "author-2"));
    }
}
```

Test trên xác minh ba điều:

1. GraphQL trả đúng tên tác giả cho từng sách.
2. Ba sách có hai author ID khác nhau được gom thành một tập ID duy nhất.
3. `AuthorCatalog.findAllById` được gọi đúng một lần trong operation này.

Sách thứ nhất và thứ ba dùng chung `author-1`. Test vẫn mong đợi cả hai parent nhận cùng tác giả nhưng repository chỉ nhận một author ID trong batch. Đây là một trường hợp tốt để kiểm tra deduplication ở tầng batch query.

Trong Spring Boot 3.x, `@GraphQlTest` thường thuộc package `org.springframework.boot.test.autoconfigure.graphql`; với Spring Boot 4.x, package test auto-configuration đã được tổ chức lại dưới `org.springframework.boot.graphql.test.autoconfigure`. `@MockitoBean` thuộc Spring Framework 6.2 trở lên; với dự án cũ hơn, dùng cơ chế mock bean tương ứng phiên bản như `@MockBean`.

Vì vậy, import trong ví dụ là dành cho Spring Boot 3.x. Với Spring Boot 4.x, thay bằng:

```java
import org.springframework.boot.graphql.test.autoconfigure.GraphQlTest;
```

## 5. Vì sao phải chọn field batch trong GraphQL document?

`@BatchMapping` chỉ chạy khi query thực sự chọn field mà nó ánh xạ. Ví dụ:

```graphql
query {
    books {
        id
        title
    }
}
```

Operation này không chọn `Book.author`, nên `author(...)` không được gọi. Nếu test chỉ query `id` và `title`, rồi verify `authorCatalog.findAllById(...)`, test sẽ thất bại đúng vì GraphQL không cần resolve field đó.

Để kiểm tra batch mapping, selection set phải có field tương ứng:

```graphql
query {
    books {
        id
        author {
            name
        }
    }
}
```

Khi cần xác minh các mapping khác nhau, viết operation có selection set đúng với field đang kiểm tra. Không nên thêm field không liên quan chỉ để kích hoạt nhiều resolver, vì sẽ làm test khó xác định nguyên nhân khi thất bại.

## 6. Kiểm tra số lần gọi và tập key của batch

Một test batch tốt thường kiểm tra cả số lần gọi và tập key:

```java
then(authorCatalog).should(times(1))
    .findAllById(Set.of("author-1", "author-2"));
```

Assertion này chứng minh service nhận một tập key duy nhất trong một lần gọi. Nếu cần kiểm tra chi tiết thứ tự hoặc nội dung key được tạo ra, có thể dùng `ArgumentCaptor`:

```java
ArgumentCaptor<Set<String>> idsCaptor = ArgumentCaptor.forClass(Set.class);

then(authorCatalog).should(times(1)).findAllById(idsCaptor.capture());

assertThat(idsCaptor.getValue())
    .containsExactlyInAnyOrder("author-1", "author-2");
```

Không dùng `containsExactly(...)` cho `Set` nếu thứ tự không phải một phần hợp đồng. `Set` không cam kết thứ tự như `List`.

Trong GraphQL execution phức tạp, một field có thể được gọi trong nhiều dispatch hoặc nhiều nhánh thực thi. Vì vậy, assertion đúng một lần phù hợp với test cụ thể có một root list và một batch dispatch. Nếu query có nhiều nhánh hoặc nhiều lần phân trang, hãy kiểm tra số batch theo cấu trúc operation thay vì áp một con số cố định cho mọi trường hợp.

## 7. Kiểm thử `@BatchMapping` trả về `Flux<V>`

`@BatchMapping` cũng có thể trả về `Flux<V>`. Khi đó, các giá trị phát ra phải theo đúng thứ tự của danh sách parent objects được truyền vào method.

Ví dụ:

```java
@BatchMapping(typeName = "Book", field = "author")
Flux<Author> author(List<Book> books) {
    List<String> authorIds = books.stream()
        .map(Book::authorId)
        .toList();

    return authorCatalog.findAllInOrder(authorIds);
}
```

Test cần xác minh thứ tự tương ứng:

```java
graphQlTester.document("""
        query {
            books {
                id
                author { name }
            }
        }
        """)
    .execute()
    .path("books[*].author.name")
    .entityList(String.class)
    .containsExactly("Ada", "Grace", "Ada");
```

Nếu repository trả kết quả theo thứ tự database tùy ý hoặc sắp xếp theo ID tác giả, kết quả có thể bị gắn nhầm parent. Khi thứ tự không được bảo đảm, `Mono<Map<K,V>>` thường dễ biểu đạt quan hệ parent-value hơn.

## 8. Kiểm tra trường hợp thiếu giá trị trong batch result

Giả sử một sách tham chiếu `authorId` không tồn tại. Với schema:

```graphql
type Book {
    id: ID!
    author: Author
}
```

Batch method có thể không đưa parent đó vào map; GraphQL sẽ trả `author: null` cho field nullable.

Test nên xác minh cả giá trị có và không có:

```java
response.path("books[0].author.name")
    .entity(String.class)
    .isEqualTo("Ada");

response.path("books[1].author").valueIsNull();
```

Nếu SDL thay thành `author: Author!`, việc phân giải thành `null` gây GraphQL execution error và null propagation lên parent nullable gần nhất. Khi test field Non-null, hãy kiểm tra cả `response.errors()` và vị trí `data` bị null theo schema.

Không dùng `Map.of(...)` để tạo map có value null vì Java `Map.of` không cho phép null key/value. Nếu cần biểu diễn giá trị null, hãy bỏ key khỏi map hoặc dùng map implementation cho phép null theo ý nghĩa của resolver.

## 9. Kiểm thử batch mapping có argument hoặc context

`@BatchMapping` hỗ trợ các method argument như:

| Argument | Ý nghĩa |
|---|---|
| `List<K>` | Danh sách parent/source objects của batch. |
| `Principal` | Principal từ Spring Security context nếu có. |
| `@ContextValue` | Một giá trị trong `GraphQLContext` của batch loader environment. |
| `GraphQLContext` | Context dùng chung của GraphQL execution. |
| `BatchLoaderEnvironment` | Context và local context của từng key trong batch. |

Ví dụ batch mapping có tenant context:

```java
@BatchMapping(typeName = "Book", field = "reviews")
Mono<Map<Book, List<Review>>> reviews(
        List<Book> books,
        @ContextValue("tenantId") String tenantId) {

    Set<String> bookIds = books.stream()
        .map(Book::id)
        .collect(Collectors.toSet());

    return reviewService.findByTenantAndBookIds(tenantId, bookIds)
        .collectMultimap(Review::bookId)
        .map(reviewsByBook -> {
            Map<Book, List<Review>> result = new LinkedHashMap<>();
            for (Book book : books) {
                result.put(book, List.copyOf(
                    reviewsByBook.getOrDefault(book.id(), List.of())
                ));
            }
            return result;
        });
}
```

Khi test context, cần khởi tạo `GraphQLContext` hoặc cấu hình request để đưa `tenantId` vào execution. Sau đó kiểm tra service nhận đúng tenant ID và toàn bộ tập book ID trong cùng batch. Không giả định test slice tự tạo tenant context hoặc Spring Security principal nếu test chưa cấu hình chúng.

## 10. Kiểm thử `BatchLoaderRegistry` và `DataLoader` trực tiếp

Khi dùng `DataLoader` trực tiếp thay cho `@BatchMapping`, có thể kiểm thử loader mà không cần chạy GraphQL query. Cách làm theo tài liệu Spring for GraphQL:

1. Tạo `DefaultBatchLoaderRegistry`.
2. Đăng ký batch loader.
3. Tạo `DataLoaderRegistry`.
4. Gọi `registerDataLoaders(...)` để đưa các loader đã đăng ký vào registry.
5. Lấy `DataLoader` theo tên.
6. Gọi `load` nhiều key, sau đó `dispatchAndJoin()` để thực hiện batch.

Ví dụ:

```java
@Test
void dispatchesSeveralKeysInOneBatch() {
    List<Set<Long>> dispatchedKeys = new ArrayList<>();

    BatchLoaderRegistry batchLoaderRegistry = new DefaultBatchLoaderRegistry();

    batchLoaderRegistry.forTypePair(Long.class, Author.class)
        .registerMappedBatchLoader((authorIds, environment) -> {
            dispatchedKeys.add(Set.copyOf(authorIds));

            return Mono.just(Map.of(
                1L, new Author("1", "Ada"),
                2L, new Author("2", "Grace"),
                3L, new Author("3", "Linus")
            ));
        });

    GraphQLContext graphQLContext = GraphQLContext.newContext().build();
    DataLoaderRegistry dataLoaderRegistry = DataLoaderRegistry.newRegistry().build();

    batchLoaderRegistry.registerDataLoaders(dataLoaderRegistry, graphQLContext);

    DataLoader<Long, Author> loader =
        dataLoaderRegistry.getDataLoader(Author.class.getName());

    loader.load(1L);
    loader.loadMany(List.of(2L, 3L));

    List<Author> authors = loader.dispatchAndJoin();

    assertThat(authors)
        .extracting(Author::name)
        .containsExactly("Ada", "Grace", "Linus");

    assertThat(dispatchedKeys)
        .containsExactly(Set.of(1L, 2L, 3L));
}
```

Các import chính:

```java
import graphql.GraphQLContext;
import org.dataloader.DataLoader;
import org.dataloader.DataLoaderRegistry;
import org.springframework.graphql.execution.BatchLoaderRegistry;
import org.springframework.graphql.execution.DefaultBatchLoaderRegistry;
import reactor.core.publisher.Mono;

import static org.assertj.core.api.Assertions.assertThat;
```

Trong ví dụ, tên mặc định của DataLoader được tạo từ class value type, tức `Author.class.getName()`. Có thể tùy chỉnh tên loader trong builder của `BatchLoaderRegistry`; nếu đã tùy chỉnh, test phải lấy loader bằng tên tương ứng.

`dispatchAndJoin()` thực hiện dispatch các key đã được queue và chờ kết quả. Test này xác minh batching của loader đã đăng ký, nhưng chưa xác minh `@BatchMapping` được bind đúng vào field GraphQL. Vì vậy, nên kết hợp với test qua `GraphQlTester` khi controller dùng annotated mapping.

## 11. Kiểm tra cache theo request của DataLoader

DataLoader thường cache kết quả theo key trong phạm vi một GraphQL request. Khi cùng key được load nhiều lần trước khi cache bị clear, batch loader không nhất thiết nhận key lặp lại.

Test có thể xác minh hành vi cache:

```java
loader.load(1L);
loader.load(1L);
loader.load(2L);

List<Author> authors = loader.dispatchAndJoin();
```

Với cache mặc định được bật, loader thường chỉ cần key `1` một lần trong batch. Nếu ứng dụng thay đổi `DataLoaderOptions` để tắt cache hoặc dùng cache strategy khác, kỳ vọng sẽ khác. Test nên mô tả rõ cấu hình loader đang dùng thay vì mặc định mọi loader đều deduplicate giống nhau.

Cache của DataLoader gắn với request, không phải cache global của ứng dụng. Không dùng một `DataLoaderRegistry` dùng chung giữa nhiều GraphQL request vì có thể làm sai phạm vi cache và dữ liệu.

## 12. Kiểm thử `BatchLoaderRegistry` có `GraphQLContext`

`BatchLoaderRegistry` hỗ trợ truyền cùng `GraphQLContext` tới batch loading function và `@BatchMapping`. Đây là một lý do Spring khuyến nghị đăng ký loader qua registry thay vì tự tạo `DataLoader` độc lập.

Ví dụ loader đọc tenant từ context:

```java
batchLoaderRegistry.forTypePair(String.class, Book.class)
    .registerMappedBatchLoader((bookIds, environment) -> {
        GraphQLContext context = (GraphQLContext) environment.getContext();
        String tenantId = context.get("tenantId");

        return bookService.findByTenantAndIds(tenantId, bookIds)
            .collectMap(Book::id);
    });
```

Trong test trực tiếp, tạo context có tenant trước khi gọi `registerDataLoaders`:

```java
GraphQLContext graphQLContext = GraphQLContext.newContext()
    .of("tenantId", "tenant-a")
    .build();
```

Sau khi dispatch, xác minh service nhận đúng tenant và tập ID. Với test `@BatchMapping`, có thể dùng `WebGraphQlTester` hoặc `ExecutionGraphQlServiceTester` để cấu hình execution context theo cách phù hợp. Mục tiêu là kiểm tra context không bị dùng chung giữa hai request tenant khác nhau.

## 13. Test `@BatchMapping` qua HTTP khi cần kiểm tra transport

`@GraphQlTest` kiểm tra GraphQL controller và execution nhưng không khởi động HTTP server. Nếu cần xác minh toàn bộ HTTP endpoint, headers, security hoặc cấu hình application context, dùng `HttpGraphQlTester` với `WebTestClient`.

Ví dụ cấu hình test với live server:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureHttpGraphQlTester
class BookBatchMappingHttpTests {

    @Autowired
    HttpGraphQlTester graphQlTester;

    @Test
    void resolvesAuthorsThroughHttp() {
        graphQlTester.document("""
                query {
                    books {
                        id
                        author { name }
                    }
                }
                """)
            .execute()
            .path("books[*].author.name")
            .entityList(String.class)
            .contains("Ada", "Grace");
    }
}
```

Test này cần application context, schema, database/fixtures và GraphQL endpoint thật được cấu hình. Nếu cần khẳng định query database chỉ chạy một lần, hãy dùng spy/metrics/query counter ở repository hoặc kiểm tra batch service; chỉ assertion response qua HTTP chưa chứng minh số lần truy vấn.

Package của `@AutoConfigureHttpGraphQlTester` cũng phụ thuộc Spring Boot:

```java
// Spring Boot 3.x
import org.springframework.boot.test.autoconfigure.graphql.tester.AutoConfigureHttpGraphQlTester;

// Spring Boot 4.x
import org.springframework.boot.graphql.test.autoconfigure.tester.AutoConfigureHttpGraphQlTester;
```

## 14. Những trường hợp nên có trong ma trận test

| Trường hợp | Điều cần xác minh |
|---|---|
| Một parent object | Mapping trả đúng associated object. |
| Nhiều parent object | Batch method nhận cả danh sách trong một dispatch. |
| Nhiều parent dùng chung key | Key được deduplicate theo cấu hình DataLoader hoặc service batch. |
| Một key không có kết quả | Nullable field thành `null`, hoặc Non-null error theo SDL. |
| Batch trả `Map<K,V>` | Mỗi parent nhận đúng value theo key. |
| Batch trả `Flux<V>` | Thứ tự value trùng thứ tự parent list. |
| Query không chọn field batch | Batch method không được gọi. |
| Có nhiều batch field | Mỗi mapping được gọi với đúng nhóm parent riêng. |
| Có `@ContextValue`/tenant | Batch query dùng đúng context của execution. |
| Hai request đồng thời | Không trộn key, cache hoặc context giữa request. |
| DataLoader cache | Key lặp được xử lý đúng theo `DataLoaderOptions`. |
| Lỗi từ repository | GraphQL error và partial data tuân theo schema. |

## 15. Lỗi thường gặp khi kiểm thử batch mapping

**Chỉ gọi method `@BatchMapping` trực tiếp.** Cách đó không kiểm tra GraphQL field registration, DataLoader dispatch hoặc mapping từ parent object. Dùng `GraphQlTester` để kiểm tra toàn bộ execution.

**Query không chọn field được batch.** Nếu document chỉ chọn `Book.id`, mapping `Book.author` sẽ không chạy. Thêm field vào selection set.

**Chỉ assert dữ liệu, không kiểm tra số lần gọi.** N+1 có thể vẫn xảy ra dù response đúng. Verify service/repository được gọi theo batch và nhận đúng tập key.

**Dùng `Flux<V>` nhưng không giữ thứ tự parent.** Kết quả có thể bị gắn sai object. Dùng `Map<K,V>` nếu không thể bảo đảm thứ tự.

**Dùng parent object làm map key nhưng không có equality ổn định.** Nếu key không có `equals`/`hashCode` phù hợp, DataLoader không thể ghép kết quả chính xác. Dùng record hoặc key bất biến.

**Lấy DataLoader bằng sai tên.** Mặc định Spring dùng class name của value type; nếu builder tùy chỉnh tên loader, test phải dùng đúng tên.

**Quên dispatch trong unit test DataLoader.** `load()` chỉ đưa key vào hàng đợi. Gọi `dispatchAndJoin()` hoặc dispatch phù hợp để thực thi batch.

**Tái sử dụng registry giữa nhiều test/request.** DataLoader cache thuộc request. Tạo registry mới cho test độc lập và tránh chia sẻ cache giữa tenant.

**Dùng mock test để kết luận SQL tối ưu.** Test batch method có thể xác minh số lần gọi service, nhưng để kiểm tra query SQL, index hoặc round-trip database cần integration test với persistence thật và query metrics.

## Kết luận

Để kiểm thử `@BatchMapping`, hãy tạo một GraphQL query chọn field cần batch, chạy qua `GraphQlTester`, kiểm tra dữ liệu trả về và xác minh service/repository nhận tập key trong số lần gọi mong đợi. Với `BatchLoaderRegistry`/`DataLoader` trực tiếp, đăng ký loader vào `DataLoaderRegistry`, queue nhiều key rồi gọi `dispatchAndJoin()` để kiểm tra kết quả batch. Bổ sung test cho key trùng, thiếu dữ liệu, thứ tự `Flux`, GraphQLContext và cache theo request. Kết hợp hai lớp kiểm thử này giúp phát hiện cả lỗi mapping lẫn lỗi batching mà response đơn thuần có thể che khuất.

## Tài liệu tham khảo

- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring for GraphQL — Request Execution: Batch Loading and Testing Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers: `@BatchMapping`](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [GraphQL Java — DataLoader](https://github.com/graphql-java/java-dataloader)
