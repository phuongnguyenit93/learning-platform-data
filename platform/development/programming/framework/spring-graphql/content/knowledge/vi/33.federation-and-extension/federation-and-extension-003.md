# Entity mapping

Trong Apollo Federation, nhiều subgraph có thể cùng đóng góp các field cho một kiểu dữ liệu. Router cần một cách để hỏi từng subgraph: “Với entity này, dựa trên khóa định danh đã biết, hãy trả về phần dữ liệu mà subgraph của bạn sở hữu.” Cơ chế đó dựa trên **entity representation** và **entity resolver**.

Với Spring for GraphQL, entity resolver được khai báo bằng `@EntityMapping`. Annotation này ánh xạ một controller method tới một kiểu entity trong schema Federation. Khi router gửi request `_entities`, Spring đọc `__typename` và các key field trong từng representation, tìm method phù hợp, bind dữ liệu đầu vào rồi gọi method để tải entity.

`@EntityMapping` và `FederationSchemaFactory` có từ Spring for GraphQL 1.3.0.

Bài học này trình bày cách bật Federation schema support, khai báo entity key, đọc representation, triển khai `@EntityMapping` theo từng entity hoặc theo batch, kết hợp `DataLoader`, xử lý lỗi và kiểm thử luồng `_entities`.

## 1. Entity trong Apollo Federation là gì?

Một entity là object type có thể được nhận diện duy nhất bằng một hoặc nhiều key field. Entity được khai báo bằng directive `@key`.

Ví dụ subgraph Books sở hữu thông tin sách:

~~~graphql
type Book @key(fields: "id") {
    id: ID!
    title: String!
    isbn: String!
}
~~~

Subgraph khác có thể đóng góp thêm field cho cùng entity `Book`, chẳng hạn thông tin đánh giá:

~~~graphql
extend type Book @key(fields: "id") {
    id: ID! @external
    averageRating: Float
    reviewCount: Int
}
~~~

Router có thể kết hợp các field từ nhiều subgraph thành một kiểu `Book` trong supergraph. Mỗi subgraph chịu trách nhiệm tải những field mà chính nó cung cấp.

Subgraph đóng góp field cho một entity phải cung cấp cách tìm lại instance entity từ key. Trong Apollo Server, cơ chế thường được gọi là `__resolveReference`; trong Spring for GraphQL, controller method `@EntityMapping` đảm nhiệm vai trò tương đương.

`@key(fields: "id")` cho router biết giá trị nào dùng để xác định một instance cụ thể. Trong ví dụ này, `id` phải định danh duy nhất một quyển sách trong phạm vi dữ liệu mà subgraph Books quản lý.

Entity là khái niệm của Federation, không phải một annotation của JPA hay một yêu cầu bắt buộc phải có class Java mang tên tương ứng. Java object trả về từ entity resolver chỉ cần được Spring/GraphQL Java ánh xạ phù hợp với GraphQL object type.

## 2. Entity representation là gì?

Khi router cần lấy thêm field của một entity từ subgraph, nó gửi một representation. Representation chứa:

- `__typename`: tên GraphQL object type cần resolve.
- Các field thuộc một `@key` hợp lệ của entity.
- Các giá trị key tương ứng với instance cần tìm.

Ví dụ representation của một quyển sách:

~~~json
{
    "__typename": "Book",
    "id": "book-42"
}
~~~

Với key gồm nhiều field:

~~~graphql
type InventoryItem @key(fields: "tenantId sku") {
    tenantId: ID!
    sku: String!
    availableQuantity: Int!
}
~~~

Representation sẽ chứa cả hai key field:

~~~json
{
    "__typename": "InventoryItem",
    "tenantId": "tenant-7",
    "sku": "SKU-100"
}
~~~

Representation chỉ cung cấp thông tin đủ để nhận diện entity. Nó không nhất thiết chứa toàn bộ dữ liệu của entity, cũng không phải bản ghi đầy đủ từ database.

Key phải định danh ổn định và duy nhất. Nếu dùng key không duy nhất, subgraph có thể trả nhầm entity và router sẽ ghép field của những object khác nhau thành một object GraphQL.

Key field không nên nhận argument và không thể là field trả về union hoặc interface. Với key ghép, mỗi field phải có giá trị đủ để subgraph tìm đúng một instance.

## 3. Router gọi entity resolver qua _entities như thế nào?

Federation subgraph có các thành phần schema đặc biệt:

- `_Any` là scalar dùng để nhận representation có hình dạng linh hoạt.
- `_Entity` là union chứa các entity type được subgraph hỗ trợ.
- `Query._entities` nhận danh sách representations và trả về các entity tương ứng.
- `Query._service` cung cấp SDL của subgraph để router khám phá schema.

Một request minh họa:

~~~graphql
query ResolveBook {
    _entities(
        representations: [
            { __typename: "Book", id: "book-42" }
            { __typename: "Book", id: "book-84" }
        ]
    ) {
        ... on Book {
            id
            title
        }
    }
}
~~~

Router gửi danh sách representation tới `_entities`. Subgraph dựa vào `__typename` để chọn entity resolver, rồi dùng key field để tải dữ liệu. Kết quả phải tương ứng với các representation đầu vào theo đúng thứ tự.

Trong Spring for GraphQL, `FederationSchemaFactory` thiết lập schema và DataFetcher/TypeResolver cần thiết cho `_entities`. Controller method có `@EntityMapping` đảm nhiệm việc tải từng entity type.

Một danh sách representation có thể chứa nhiều `__typename` khác nhau. Spring định tuyến từng representation tới entity mapping tương ứng; một method nhận `List` thường xử lý batch cho một entity type cụ thể.

Bạn không cần tự viết resolver cho `Query._entities` nếu đã dùng integration của Spring for GraphQL.

## 4. Bật Federation support trong Spring for GraphQL

Spring for GraphQL tích hợp với thư viện `federation-jvm` để tạo schema tương thích Apollo Federation. Với Spring Boot, khai báo `FederationSchemaFactory` bean và kết nối nó với `GraphQlSource` bằng `GraphQlSourceBuilderCustomizer`.

~~~java
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.data.federation.FederationSchemaFactory;

@Configuration(proxyBeanMethods = false)
public class FederationConfiguration {

    @Bean
    FederationSchemaFactory federationSchemaFactory() {
        return new FederationSchemaFactory();
    }

    @Bean
    GraphQlSourceBuilderCustomizer federationSchemaCustomizer(
            FederationSchemaFactory factory) {

        return builder ->
                builder.schemaFactory(factory::createGraphQLSchema);
    }
}
~~~

`FederationSchemaFactory` phát hiện các controller method được đánh dấu `@EntityMapping` và tạo schema Federation tương ứng. Nó cần được khai báo trong Spring configuration để nhận ApplicationContext và tìm controller.

Package của `GraphQlSourceBuilderCustomizer` thay đổi theo Spring Boot major version: với Spring Boot 3.x dùng `org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer`; với Spring Boot 4.x dùng `org.springframework.boot.graphql.autoconfigure.GraphQlSourceBuilderCustomizer`. Phần còn lại của cấu hình giữ nguyên.

Nếu dùng Apollo Federation 2, SDL của subgraph còn cần khai báo `@link` với phiên bản Federation và import các directive được sử dụng. Ví dụ rút gọn:

~~~graphql
extend schema
    @link(
        url: "https://specs.apollo.dev/federation/v2.0"
        import: ["@key", "@external"]
    )

type Book @key(fields: "id") {
    id: ID!
    title: String!
}
~~~

Khi subgraph chỉ extend entity do subgraph khác sở hữu, cần khai báo key field là external theo schema Federation đang dùng. Hãy đồng bộ Federation version và directive import giữa các subgraph trước khi compose supergraph.

## 5. Viết entity resolver đầu tiên bằng @EntityMapping

Giả sử schema có entity `Book` với key `id`:

~~~graphql
type Book @key(fields: "id") {
    id: ID!
    title: String!
    isbn: String!
}
~~~

Controller có thể khai báo method:

~~~java
import org.springframework.graphql.data.federation.EntityMapping;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.stereotype.Controller;

@Controller
public class BookEntityController {

    private final BookService bookService;

    public BookEntityController(BookService bookService) {
        this.bookService = bookService;
    }

    @EntityMapping
    public Book book(@Argument String id) {
        return bookService.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }
}
~~~

Spring nhận representation của entity `Book`, lấy giá trị key `id` rồi bind vào tham số `@Argument`. Method trả về object `Book` để GraphQL tiếp tục resolve những field được chọn.

Trong ví dụ này, tên method là `book`. Mặc định, Spring viết hoa chữ cái đầu để suy ra tên entity `Book`. Vì vậy method được ánh xạ tới GraphQL type `Book`.

`@EntityMapping` chỉ xử lý bước khôi phục entity từ representation. Những field khác của entity vẫn có thể dùng `@SchemaMapping`, `@BatchMapping` hoặc property access thông thường.

## 6. Chỉ định rõ tên entity bằng @EntityMapping

Khi tên method không tương ứng với tên GraphQL type, hãy chỉ định tên entity:

~~~java
@EntityMapping(name = "Book")
public Book loadBook(@Argument String id) {
    return bookService.findById(id)
            .orElseThrow(() -> new BookNotFoundException(id));
}
~~~

`value` là alias của thuộc tính `name`, do đó `@EntityMapping("Book")` cũng có thể dùng để chỉ định tên.

Nếu không chỉ định, Spring dùng tên method và viết hoa ký tự đầu. Ví dụ:

| Method | Entity type mặc định |
| --- | --- |
| `book(...)` | `Book` |
| `product(...)` | `Product` |
| `inventoryItem(...)` | `InventoryItem` |

Tên entity phải khớp chính xác với object type trong SDL. Nếu representation có `__typename` là `Book` nhưng không có method tương ứng, Spring không thể định tuyến representation tới controller handler.

## 7. Bind key field bằng @Argument hoặc toàn bộ representation bằng Map

Với key đơn giản, `@Argument` giúp lấy trực tiếp giá trị key:

~~~java
@EntityMapping
public Book book(@Argument String id) {
    return bookService.findById(id)
            .orElseThrow(() -> new BookNotFoundException(id));
}
~~~

Khi entity dùng composite key hoặc cần kiểm tra thêm metadata, có thể nhận toàn bộ representation:

~~~java
@EntityMapping
public InventoryItem inventoryItem(Map<String, Object> representation) {
    String tenantId = (String) representation.get("tenantId");
    String sku = (String) representation.get("sku");

    return inventoryService.findByTenantAndSku(tenantId, sku)
            .orElseThrow(() ->
                    new InventoryItemNotFoundException(tenantId, sku));
}
~~~

Map representation cũng chứa `__typename`. Nếu cần kiểm tra type hoặc hỗ trợ nhiều key format, có thể đọc giá trị đó trong method.

Spring còn hỗ trợ các tham số như `GraphQLContext`, `@ContextValue`, `@LocalContextValue`, `Principal`, `@AuthenticationPrincipal`, `DataFetchingFieldSelectionSet`, `Locale` và `DataFetchingEnvironment`.

Những tham số này hữu ích khi entity lookup phụ thuộc tenant, người dùng hiện tại, locale hoặc selection set. Không nên lấy dữ liệu định danh từ context thay cho key nếu schema contract yêu cầu representation phải cung cấp key rõ ràng.

## 8. Xử lý composite key và nhiều key

Một entity có thể có key gồm nhiều field:

~~~graphql
type ProductVariant @key(fields: "productId variantCode") {
    productId: ID!
    variantCode: String!
    displayName: String!
}
~~~

Method nhận toàn bộ representation:

~~~java
@EntityMapping
public ProductVariant productVariant(Map<String, Object> representation) {
    String productId = (String) representation.get("productId");
    String variantCode = (String) representation.get("variantCode");

    return variantService.find(productId, variantCode)
            .orElseThrow(() ->
                    new ProductVariantNotFoundException(productId, variantCode));
}
~~~

Một entity cũng có thể khai báo nhiều `@key` nếu Federation version và schema composition cho phép:

~~~graphql
type Product @key(fields: "id") @key(fields: "sku") {
    id: ID!
    sku: String!
    name: String!
}
~~~

Trong trường hợp này, router có thể gửi representation dựa trên key phù hợp. Entity resolver phải hiểu các dạng representation mà subgraph công bố hỗ trợ.

Với nhiều key khác nhau, nhận `Map<String, Object>` thường rõ ràng hơn việc giả định chỉ có một argument tên `id`. Hãy kiểm tra key field có đủ, đúng kiểu và có thể truy vấn hiệu quả trong persistence layer.

## 9. Resolve nhiều representation cùng lúc

Một request `_entities` có thể chứa nhiều representation cùng kiểu. Spring for GraphQL cho phép entity mapping method nhận một danh sách key và trả về danh sách entity:

~~~java
@EntityMapping
public List<Book> book(@Argument List<String> idList) {
    List<Book> loadedBooks = bookRepository.findAllById(idList);

    Map<String, Book> byId = loadedBooks.stream()
            .collect(Collectors.toMap(Book::id, Function.identity()));

    return idList.stream()
            .map(id -> {
                Book book = byId.get(id);
                if (book == null) {
                    throw new BookNotFoundException(id);
                }
                return book;
            })
            .toList();
}
~~~

Tên tham số `idList` giúp Spring nhận ra đây là danh sách giá trị của key `id`. Quy ước này hỗ trợ bỏ hậu tố số nhiều `List` để xác định tên argument. Có thể đặt tên argument tường minh bằng `@Argument("id")` nếu cần.

Điểm quan trọng là danh sách trả về phải giữ đúng thứ tự của các key đầu vào. `findAllById` hoặc câu SQL `IN (...)` không phải lúc nào cũng bảo đảm thứ tự giống danh sách ID đã truyền. Vì vậy ví dụ tạo map theo ID rồi dựng lại danh sách theo `idList`.

Nếu trả về kết quả sai thứ tự, router có thể gắn field của một entity vào representation khác. Đây là lỗi dữ liệu nghiêm trọng dù từng object trả về đều hợp lệ.

## 10. Nhận toàn bộ danh sách representation

Nếu một method cần xử lý nhiều representation và nhiều key field, có thể nhận `List<Map<String, Object>>`:

~~~java
@EntityMapping
public List<Book> book(List<Map<String, Object>> representations) {
    List<String> ids = representations.stream()
            .map(representation -> (String) representation.get("id"))
            .toList();

    Map<String, Book> byId = bookService.findAllByIds(ids).stream()
            .collect(Collectors.toMap(Book::id, Function.identity()));

    return ids.stream()
            .map(id -> {
                Book book = byId.get(id);
                if (book == null) {
                    throw new BookNotFoundException(id);
                }
                return book;
            })
            .toList();
}
~~~

Dạng này cung cấp toàn bộ representation của từng entity. Nó hữu ích khi một controller method cần tự xử lý nhiều dạng key hoặc cần đọc thêm metadata từ representation.

Cần giữ nguyên thứ tự đầu vào khi tạo danh sách kết quả. Nếu representation có nhiều key field, hãy tạo khóa composite hoặc gọi service bằng đúng tập field cần thiết; không nên chỉ lấy `id` nếu SDL không định nghĩa đó là key.

## 11. Dùng DataLoader để tránh N+1 khi resolve entity

Nếu mỗi representation kích hoạt một lần truy vấn database hoặc một HTTP call, request có 100 entity có thể tạo ra 100 lần I/O. Đây là vấn đề N+1 ở bước entity lookup.

Spring for GraphQL cung cấp `BatchLoaderRegistry` để đăng ký batch loader. Có thể inject registry vào controller hoặc configuration:

Spring Boot GraphQL starter cung cấp sẵn bean `BatchLoaderRegistry`, vì vậy có thể inject trực tiếp như ví dụ dưới đây.

~~~java
import org.dataloader.DataLoader;
import org.springframework.graphql.execution.BatchLoaderRegistry;
import org.springframework.stereotype.Controller;

@Controller
public class BookEntityController {

    public BookEntityController(
            BatchLoaderRegistry registry,
            BookService bookService) {

        registry.forTypePair(String.class, Book.class)
                .registerMappedBatchLoader((ids, environment) ->
                        bookService.findAllByIds(ids)
                                .collectMap(Book::id));
    }

    @EntityMapping
    public CompletableFuture<Book> book(
            @Argument String id,
            DataLoader<String, Book> dataLoader) {

        return dataLoader.load(id);
    }
}
~~~

`registerMappedBatchLoader` nhận một tập key và trả `Mono<Map<K, V>>`. Cách này phù hợp khi database không có kết quả cho một số key, vì map chỉ chứa những key tìm thấy.

Trong ví dụ trên, giả sử `BookService.findAllByIds` trả về `Flux<Book>`. Nếu service dùng JPA đồng bộ, hãy chuyển lời gọi blocking sang executor phù hợp thay vì chạy trực tiếp trên event loop của WebFlux.

Spring đăng ký DataLoader theo request. Các lời gọi `load(id)` được gom lại và batch loader có thể tải nhiều entity trong một lần truy cập dữ liệu. DataLoader cũng cache kết quả theo key trong phạm vi request.

Không tạo một DataLoader dùng chung cho toàn bộ ứng dụng. Cache theo request giúp tránh rò rỉ dữ liệu giữa người dùng hoặc tenant và giới hạn vòng đời dữ liệu trong một GraphQL operation.

## 12. registerBatchLoader và registerMappedBatchLoader khác nhau thế nào?

`BatchLoaderRegistry` có hai cách đăng ký thường dùng:

| API | Dữ liệu trả về | Khi nào dùng |
| --- | --- | --- |
| `registerBatchLoader` | `Flux<V>` có số lượng và thứ tự khớp danh sách key đầu vào | Mọi key phải có một vị trí kết quả tương ứng |
| `registerMappedBatchLoader` | `Mono<Map<K, V>>` ánh xạ key sang giá trị | Một số key có thể không có entity |

Ví dụ với `registerBatchLoader`:

~~~java
registry.forTypePair(String.class, Book.class)
        .registerBatchLoader((ids, environment) ->
                bookService.findAllByIdsInRequestedOrder(ids));
~~~

Hàm `findAllByIdsInRequestedOrder` phải trả kết quả đúng số lượng và thứ tự key; nếu không tìm thấy entity, vị trí tương ứng phải là `null` theo contract của batch loader.

Với `registerMappedBatchLoader`, kết quả là map theo key nên thứ tự của map không phải cơ chế ghép kết quả. DataLoader tự ghép từng giá trị theo key. Đây thường là lựa chọn tiện hơn cho entity lookup khi có thể tồn tại ID không còn trong hệ thống.

## 13. Kết hợp @EntityMapping với @SchemaMapping và @BatchMapping

`@EntityMapping` chỉ khôi phục object entity từ representation. Các field khác vẫn được resolve bằng cơ chế mapping thông thường.

Ví dụ entity `Book` có field `author`:

~~~java
@Controller
public class BookController {

    @EntityMapping
    public Book book(@Argument String id) {
        return bookService.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }
}
~~~

Nếu request lấy nhiều Book và mỗi Book có một Author, resolver trên có thể tạo N+1 query. Có thể dùng `@BatchMapping`:

~~~java
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import reactor.core.publisher.Mono;

@BatchMapping(typeName = "Book", field = "author")
public Mono<Map<Book, Author>> author(List<Book> books) {
    Set<String> authorIds = books.stream()
            .map(Book::authorId)
            .collect(Collectors.toSet());

    return authorService.findAllByIds(authorIds)
            .collectMap(Author::id)
            .map(byId -> {
                Map<Book, Author> result = new HashMap<>();
                for (Book book : books) {
                    Author author = byId.get(book.authorId());
                    if (author != null) {
                        result.put(book, author);
                    }
                }
                return result;
            });
}
~~~

Ví dụ bỏ qua những Book không có Author tương ứng, nên field `author` cần nullable trong SDL. Nếu field được khai báo non-null, hãy chuyển trường hợp thiếu Author thành exception theo error contract của API.

`@BatchMapping` là shortcut cho các trường hợp batch load field đơn giản. Entity mapping và batch mapping giải quyết hai bước khác nhau:

- `@EntityMapping` tải entity dựa trên representation mà router gửi.
- `@BatchMapping` tải các field liên quan cho nhiều parent entity cùng lúc.
- `DataLoader` có thể được dùng trực tiếp trong entity mapping hoặc schema mapping khi cần kiểm soát linh hoạt hơn.

Nếu dùng object `Book` làm key của map trong `@BatchMapping`, class đó cần có `equals` và `hashCode` ổn định.

## 14. Hỗ trợ reactive và asynchronous return types

Entity mapping method có thể trả về entity trực tiếp hoặc kiểu bất đồng bộ được Spring hỗ trợ:

- Entity object.
- `Mono<T>`.
- `CompletableFuture<T>`.
- `Callable<T>`.

Ví dụ reactive:

~~~java
@EntityMapping
public Mono<Book> book(@Argument String id) {
    return bookRepository.findById(id);
}
~~~

Ví dụ asynchronous:

~~~java
@EntityMapping
public CompletableFuture<Book> book(@Argument String id) {
    return bookService.findByIdAsync(id);
}
~~~

Với reactive repository, trả `Mono` trực tiếp giúp Spring xử lý pipeline mà không cần block. Với `DataLoader`, `CompletableFuture` là kiểu return tự nhiên từ `load`.

Không gọi `block()` bên trong resolver trên WebFlux event loop. Việc block có thể làm nghẽn thread xử lý request và khiến các request Federation khác bị chậm theo.

## 15. Entity không tồn tại và xử lý lỗi representation

Spring for GraphQL có các exception riêng cho bước resolve representation:

| Exception | Nguyên nhân |
| --- | --- |
| `RepresentationException` | Thiếu `__typename` hoặc không tìm được controller method tương ứng với entity type |
| `RepresentationNotResolvedException` | Entity mapping method trả về `null` hoặc reactive/async result hoàn tất rỗng |

Nếu method trả `null`, Spring không đơn giản bỏ qua representation. Nó phát sinh `RepresentationNotResolvedException` để biểu thị entity không được resolve.

Ví dụ chủ động ném exception nghiệp vụ:

~~~java
@EntityMapping
public Book book(@Argument String id) {
    return bookService.findById(id)
            .orElseThrow(() -> new BookNotFoundException(id));
}
~~~

Có thể dùng `@GraphQlExceptionHandler` trong controller hoặc `@ControllerAdvice` để chuyển exception từ entity mapping thành `GraphQLError`. Error sẽ xuất hiện trong response của operation `_entities`.

Không nên trả object rỗng hoặc object giả chỉ để tránh lỗi. Nếu key không tồn tại hoặc người gọi không có quyền truy cập, hãy áp dụng chính sách lỗi nhất quán với API và bảo đảm không làm lộ thông tin nhạy cảm.

## 16. Context, tenant và authorization khi resolve entity

Entity representation đến từ router nhưng vẫn là dữ liệu đầu vào của request. Không được mặc định rằng có key hợp lệ nghĩa là người gọi có quyền đọc entity đó.

Entity mapping method có thể nhận `Principal`, `@AuthenticationPrincipal` hoặc `GraphQLContext`. Ví dụ:

~~~java
@EntityMapping
public Book book(
        @Argument String id,
        Principal principal,
        @ContextValue("tenantId") String tenantId) {

    return bookService.findVisibleBook(id, tenantId, principal)
            .orElseThrow(() -> new BookNotFoundException(id));
}
~~~

Trong ứng dụng multi-tenant, truy vấn phải giới hạn theo tenant của người dùng hiện tại. Không chỉ tìm theo `id` rồi trả object bất kể tenant.

Subgraph thường nên chỉ nhận request từ router hoặc service gateway đáng tin cậy. Nếu endpoint subgraph được public trực tiếp, client có thể gọi `_entities` bằng representation tự tạo và thử truy xuất entity. Hãy bảo vệ bằng network policy, service-to-service authentication và authorization tại resolver.

Không đưa secret, credential hoặc thông tin phân quyền vào representation. Representation chỉ nên chứa key và dữ liệu định danh cần thiết cho Federation.

## 17. Kiểm thử entity mapping bằng GraphQlTester

Có thể kiểm thử `_entities` trực tiếp bằng `GraphQlTester` hoặc một tester cụ thể như `WebGraphQlTester`. Ví dụ:

~~~java
@Test
void resolvesBookFromFederationRepresentation() {
    graphQlTester.document("""
            query ResolveBook($representations: [_Any!]!) {
                _entities(representations: $representations) {
                    ... on Book {
                        id
                        title
                    }
                }
            }
            """)
            .variable("representations", List.of(
                    Map.of(
                            "__typename", "Book",
                            "id", "book-42"
                    )
            ))
            .execute()
            .path("_entities[0].id")
            .entity(String.class)
            .isEqualTo("book-42");
}
~~~

Test này kiểm tra cả Federation schema wiring lẫn controller method được ánh xạ bởi `@EntityMapping`.

Nên kiểm thử thêm:

- Representation có `__typename` và key hợp lệ.
- Representation thiếu `__typename`.
- `__typename` không có entity mapping tương ứng.
- Entity key không tồn tại.
- Composite key được bind đầy đủ.
- Nhiều representation trả kết quả đúng thứ tự.
- DataLoader batch nhiều key trong một lần gọi service.
- User/tenant không có quyền truy cập entity.
- Exception từ entity mapping được chuyển thành GraphQL error như mong đợi.

## 18. Kiểm thử thứ tự và batch loading

Thứ tự là một phần của contract khi entity mapping nhận danh sách representation. Có thể cố ý gửi ID theo thứ tự khác với database:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.graphql.test.tester.GraphQlTester;

class FederationEntityMappingTests {

    private final GraphQlTester graphQlTester;

    @Autowired
    FederationEntityMappingTests(GraphQlTester graphQlTester) {
        this.graphQlTester = graphQlTester;
    }

    record BookView(String id) {
    }

    @Test
    void preservesRepresentationOrder() {
        graphQlTester.document("""
                query ResolveBooks($representations: [_Any!]!) {
                    _entities(representations: $representations) {
                        ... on Book {
                            id
                        }
                    }
                }
                """)
                .variable("representations", List.of(
                        Map.of("__typename", "Book", "id", "book-84"),
                        Map.of("__typename", "Book", "id", "book-42")
                ))
                .execute()
                .path("_entities")
                .entityList(BookView.class)
                .satisfies(books -> {
                    assertThat(books).extracting(BookView::id)
                            .containsExactly("book-84", "book-42");
                });
    }
}
~~~

Để kiểm tra DataLoader batch, có thể dùng mock service và xác minh nó nhận tập key nhiều phần tử trong cùng một lần gọi. Tránh chỉ kiểm tra response đúng; response đúng vẫn có thể được tạo ra bởi N lần truy vấn riêng.

Trong integration test, có thể ghi nhận số lần repository hoặc HTTP client được gọi. Với một request có nhiều representation cùng entity type, batch loader nên nhận nhiều key trong một lần dispatch nếu chúng nằm trong cùng batch window.

## 19. Các lỗi thường gặp khi triển khai Entity mapping

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `_entities` không có trong schema | Chưa dùng `FederationSchemaFactory` khi tạo `GraphQlSource` | Đăng ký factory và schema customizer |
| Không tìm được handler cho entity | `__typename` không khớp tên entity mapping | Đổi tên method hoặc đặt `@EntityMapping(name = "...")` |
| Key argument nhận null | Tên `@Argument` không khớp key trong representation | Kiểm tra tên field và dùng `@Argument("id")` rõ ràng |
| Composite key không resolve | Method chỉ nhận một key trong khi `@key` có nhiều field | Nhận toàn bộ representation bằng Map |
| Kết quả batch gắn nhầm entity | Danh sách kết quả khác thứ tự representation | Dựng lại kết quả theo danh sách key đầu vào |
| Entity mapping tạo N+1 | Mỗi representation tự gọi repository/service riêng | Dùng list mapping hoặc DataLoader |
| Method trả null gây lỗi | Representation không tìm được entity | Xử lý missing entity theo error contract |
| Entity field bị null | `@SchemaMapping` hoặc `@BatchMapping` chưa được cấu hình đúng | Kiểm tra source object, field name và mapping |
| Test _entities_ thất bại trước resolver | Federation schema wiring hoặc query type không hợp lệ | Kiểm tra factory, SDL, key và inline fragment |
| Entity lộ dữ liệu tenant khác | Resolver tin tưởng key mà không kiểm tra quyền | Kiểm tra principal/tenant tại service hoặc resolver |
| Service bị gọi nhiều lần dù có DataLoader | Key type/name không khớp hoặc loader chưa được đăng ký theo request | Đồng bộ generic key/value và BatchLoaderRegistry |

## 20. Quy trình xây dựng Entity mapping

Khi thêm một entity vào subgraph Spring for GraphQL, có thể làm theo thứ tự:

1. Xác định object type nào cần được nhiều subgraph chia sẻ.
2. Chọn key field duy nhất và ổn định cho entity.
3. Khai báo `@key` trong SDL theo Federation version đang dùng.
4. Bật Federation support bằng `FederationSchemaFactory`.
5. Viết controller method `@EntityMapping` cho entity type.
6. Bind key bằng `@Argument` hoặc nhận toàn bộ representation bằng Map.
7. Nếu nhận nhiều representation, giữ đúng thứ tự kết quả.
8. Dùng DataLoader hoặc list entity mapping để tránh N+1.
9. Dùng `@SchemaMapping` hoặc `@BatchMapping` để resolve các field còn lại.
10. Kiểm tra missing entity, exception và authorization theo tenant/user.
11. Kiểm thử operation `_entities` với representation hợp lệ, không hợp lệ và nhiều key.
12. Đảm bảo subgraph endpoint được bảo vệ và router có thể truy cập đúng transport.

## 21. Những điểm cần ghi nhớ

- Entity là object type có key, được đánh dấu bằng `@key`.
- Representation chứa `__typename` và các key field cần để xác định entity.
- Router gọi `_entities` để yêu cầu subgraph resolve entity.
- `FederationSchemaFactory` tạo Federation schema và wiring cho `_entities`.
- `@EntityMapping` ánh xạ controller method tới entity type.
- `@Argument` lấy một key field; `Map<String, Object>` cung cấp toàn bộ representation.
- Entity mapping có thể nhận nhiều key/representation và phải giữ đúng thứ tự trả về.
- DataLoader giúp gom entity lookup, giảm N+1 và cache trong phạm vi request.
- `@SchemaMapping` và `@BatchMapping` tiếp tục xử lý các field khác của entity.
- Null hoặc empty return được Spring biểu diễn bằng `RepresentationNotResolvedException`.
- Luôn kiểm tra authorization theo user/tenant; không tin tưởng representation như bằng chứng quyền truy cập.

Entity mapping là cầu nối giữa entity key trong Federation schema và dữ liệu thực tế trong từng subgraph. Khi key được thiết kế ổn định, representation được bind đúng, kết quả batch giữ đúng thứ tự và DataLoader được dùng hợp lý, các subgraph có thể đóng góp field cho cùng một entity mà vẫn giữ quyền sở hữu dữ liệu rõ ràng.

## Tài liệu tham khảo

- [Spring for GraphQL — Federation](https://docs.spring.io/spring-graphql/reference/federation.html)
- [Spring for GraphQL — FederationSchemaFactory API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/federation/FederationSchemaFactory.html)
- [Spring for GraphQL — EntityMapping API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/federation/EntityMapping.html)
- [Spring for GraphQL — Request Execution and Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Apollo Federation — Introduction to Entities](https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/entities/intro)
- [Apollo Federation — Subgraph Specification](https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/reference/subgraph-spec)
