# `@EntityMapping` trong Spring for GraphQL

`@EntityMapping` là annotation của Spring for GraphQL dùng để tải một entity khi subgraph nhận yêu cầu phân giải entity từ Federation gateway. Trong Apollo Federation, một entity có thể được nhiều subgraph cùng đóng góp field. Gateway dùng các field khóa của entity để chuyển một phần kết quả từ subgraph này sang subgraph khác; subgraph nhận representation phải biến nó thành đối tượng Java để tiếp tục resolve các field mà subgraph đó sở hữu.

`@EntityMapping` nối representation của Federation với model và service trong ứng dụng Spring. Nó xử lý bước tìm hoặc tạo entity reference theo khóa; các field còn lại của entity vẫn có thể được resolve bằng `@SchemaMapping`, `@BatchMapping` hoặc DataLoader.

## Entity và representation trong Federation

Trong một supergraph, mỗi subgraph là một GraphQL service độc lập. Nhiều subgraph có thể định nghĩa cùng một entity và đóng góp các field khác nhau. Directive `@key` khai báo tập field dùng để nhận diện một instance entity.

Ví dụ, subgraph Products cung cấp thông tin sách:

```graphql
extend schema
  @link(
    url: "https://specs.apollo.dev/federation/v2.3"
    import: ["@key"]
  )

type Query {
  bookById(id: ID!): Book
}

type Book @key(fields: "id") {
  id: ID!
  title: String!
}
```

Subgraph Reviews có thể đóng góp field `reviews` cho cùng entity `Book`:

```graphql
extend schema
  @link(
    url: "https://specs.apollo.dev/federation/v2.3"
    import: ["@key"]
  )

type Query {
  reviewsForBook(bookId: ID!): [Review!]!
}

type Book @key(fields: "id") {
  id: ID!
  reviews: [Review!]!
}

type Review {
  id: ID!
  body: String!
}
```

Trong Federation 2, subgraph Reviews khai báo `Book` với cùng key và field mà nó cung cấp. Không cần dùng `@extends` hoặc đánh dấu key field bằng `@external` như kiểu schema mở rộng của Federation 1. Federation 2 dùng `@link` để import các directive cần thiết.

Khi gateway cần lấy `Book.reviews`, nó gửi representation của entity tới subgraph Reviews. Representation thường là một map JSON có `__typename` và các field trong key:

```json
{
  "__typename": "Book",
  "id": "book-10"
}
```

`__typename` cho biết representation thuộc GraphQL type nào; `id` là key để nhận diện entity. Nếu key gồm nhiều field, representation phải chứa đủ tất cả field đó. Gateway không nhất thiết gửi toàn bộ object; subgraph cần dùng key để tải hoặc tạo reference tối thiểu.

## Gateway gọi `_entities` như thế nào?

Apollo Federation định nghĩa các field nội bộ cho subgraph, trong đó có:

- `Query._entities(representations: [_Any!]!): [_Entity]!` nhận danh sách entity representations và trả entity tương ứng.
- `Query._service { sdl }` cung cấp SDL của subgraph để gateway đọc và compose schema.
- `_Any` là scalar đại diện cho map representation.
- `_Entity` là union chứa các object type được đánh dấu `@key` và có thể resolve trong subgraph.

Ví dụ request nội bộ tương đương gateway có thể gửi:

```graphql
query ResolveEntities($representations: [_Any!]!) {
  _entities(representations: $representations) {
    ... on Book {
      id
      reviews {
        id
        body
      }
    }
  }
}
```

```json
{
  "representations": [
    {
      "__typename": "Book",
      "id": "book-10"
    }
  ]
}
```

Ứng dụng client thông thường gọi operation nghiệp vụ ở supergraph. Gateway tự xây dựng các lời gọi `_entities` tới subgraph theo query plan; client không cần tự gọi `_entities` trong ứng dụng.

## `@EntityMapping` làm nhiệm vụ gì?

`@EntityMapping` đăng ký một controller method làm entity resolver cho một GraphQL type. Spring for GraphQL dùng `FederationSchemaFactory` để phát hiện các method này và gắn chúng vào `_entities` DataFetcher.

Ví dụ trong subgraph Reviews, chỉ cần tạo một `Book` reference từ key `id`. Sau đó `@SchemaMapping` dùng ID để lấy danh sách review:

```java
import org.springframework.graphql.data.federation.EntityMapping;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;
import java.util.List;

@Controller
public class BookEntityController {

    private final ReviewService reviewService;

    public BookEntityController(ReviewService reviewService) {
        this.reviewService = reviewService;
    }

    @EntityMapping(name = "Book")
    public Book book(@Argument("id") String id) {
        return new Book(id);
    }

    @SchemaMapping(typeName = "Book", field = "reviews")
    public List<Review> reviews(Book book) {
        return reviewService.findByBookId(book.id());
    }
}

public record Book(String id) {
}
```

Ở đây, `@EntityMapping` không cần tải toàn bộ Book từ database. Nó chỉ tạo đối tượng reference có key `id`, đủ để `@SchemaMapping` truy vấn review theo ID. Đây là cách hữu ích khi subgraph đóng góp một field quan hệ và dữ liệu cục bộ chỉ cần key của entity.

Nếu logic nghiệp vụ cần xác nhận Book tồn tại hoặc cần thuộc tính khác để kiểm tra quyền, hãy tải entity từ service thay vì tạo reference mù. Việc entity resolver chỉ tạo reference hay tải toàn bộ entity phụ thuộc vào dữ liệu mà các field do subgraph sở hữu cần dùng.

## Tên entity được ánh xạ

Mặc định, Spring lấy tên method và viết hoa chữ cái đầu để suy ra tên GraphQL entity. Ví dụ method `book(...)` ánh xạ tới type `Book`; method `product(...)` ánh xạ tới `Product`.

Có thể chỉ định tên rõ ràng bằng `@EntityMapping(name = "Book")`. Thuộc tính `value` là alias của `name`:

```java
@EntityMapping("Book")
public Book resolveBook(@Argument("id") String id) {
    return new Book(id);
}
```

Dùng tên tường minh khi method có tên khác quy ước, khi nhiều entity được resolve trong cùng controller hoặc khi muốn tránh nhầm lẫn giữa tên Java class và GraphQL type.

`@EntityMapping` thuộc package `org.springframework.graphql.data.federation`, khác package với `@SchemaMapping` và `@QueryMapping` trong `org.springframework.graphql.data.method.annotation`.

## Bật Federation cho GraphQlSource

Để `@EntityMapping` hoạt động, schema cần được tạo bằng `FederationSchemaFactory`. Factory này tích hợp với thư viện `federation-jvm`, phát sinh các thành phần Federation như `_Entity`, `_Any`, `_service`, `_entities` và type resolver tương ứng.

Thêm dependency Federation JVM tương thích với dòng Spring for GraphQL và GraphQL Java mà dự án đang sử dụng:

```kotlin
dependencies {
    implementation("org.springframework.graphql:spring-graphql")
    implementation("com.apollographql.federation:federation-graphql-java-support:$federationJvmVersion")
}
```

Trong ứng dụng Spring Boot, khai báo `FederationSchemaFactory` và một `GraphQlSourceBuilderCustomizer`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.data.federation.FederationSchemaFactory;
// Spring Boot 4.x:
import org.springframework.boot.graphql.autoconfigure.GraphQlSourceBuilderCustomizer;
// Spring Boot 3.x dùng package:
// org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;

@Configuration(proxyBeanMethods = false)
public class FederationConfiguration {

    @Bean
    FederationSchemaFactory federationSchemaFactory() {
        return new FederationSchemaFactory();
    }

    @Bean
    GraphQlSourceBuilderCustomizer federationSchemaCustomizer(
            FederationSchemaFactory factory) {
        return builder -> builder.schemaFactory(factory::createGraphQLSchema);
    }
}
```

`$federationJvmVersion` là version property do dự án quản lý. Chọn bản `federation-graphql-java-support` tương thích với phiên bản Spring for GraphQL/GraphQL Java; không tự động lấy version mới nhất nếu nó nâng major GraphQL Java.

Spring Boot vẫn tự cấu hình schema resources, annotated controllers và các `RuntimeWiringConfigurer` bean. Customizer chỉ thay schema factory để Federation có thể bổ sung các thành phần subgraph. Nếu ứng dụng tự tạo `GraphQlSource` mà không dùng Boot auto-configuration, truyền `factory::createGraphQLSchema` trực tiếp vào `GraphQlSource` builder và giữ lại các runtime wiring configurer hiện có.

Không khai báo một `GraphQlSource` thứ hai chỉ để bật Federation nếu Boot đã tạo nguồn schema. Cần tùy chỉnh builder hiện tại để tránh làm mất schema, controller mappings, scalar hoặc exception resolvers khác.

## Method signature của `@EntityMapping`

Entity mapping method hỗ trợ nhiều kiểu tham số, tùy dữ liệu mà resolver cần:

| Tham số | Mục đích |
| --- | --- |
| `@Argument` | Lấy một field cụ thể từ representation và bind sang kiểu Java. |
| `Map<String, Object>` | Nhận toàn bộ representation của một entity, gồm `__typename` và key fields. |
| `List<Map<String, Object>>` | Nhận toàn bộ danh sách representations khi một method xử lý nhiều entity cùng type. |
| `GraphQLContext` | Đọc context chung của GraphQL execution. |
| `@ContextValue` / `@LocalContextValue` | Đọc giá trị từ GraphQL context hoặc local context. |
| `Principal` / `@AuthenticationPrincipal` | Đọc danh tính đã xác thực nếu Spring Security context có sẵn. |
| `DataLoader<I, E>` | Tải entity qua DataLoader theo key. |
| `DataFetchingEnvironment` | Truy cập trực tiếp execution environment khi cần. |
| `DataFetchingFieldSelectionSet` | Kiểm tra selection set của entity query. |
| `Locale` | Đọc locale của request. |

Ví dụ nhận toàn representation:

```java
@EntityMapping(name = "Book")
public Book book(Map<String, Object> representation) {
    String id = (String) representation.get("id");
    String tenantId = (String) representation.get("tenantId");
    return new Book(id, tenantId);
}
```

Chỉ đọc các key field thực sự có trong schema và representation. Không giả định gateway luôn gửi mọi field của entity; representation được xây từ `@key` và các field mà query plan cần chuyển qua subgraph.

Các method có thể trả entity trực tiếp hoặc kiểu bất đồng bộ như `Mono<T>`, `CompletableFuture<T>` và `Callable<T>`. Chọn kiểu trả về phù hợp với cách truy cập dữ liệu; không block event-loop khi dùng reactive transport.

## Key đơn và key ghép

Với entity có một key, có thể bind trực tiếp vào một tham số:

```graphql
type Product @key(fields: "upc") {
  upc: ID!
  name: String!
}
```

```java
@EntityMapping
public Product product(@Argument("upc") String upc) {
    return productService.findByUpc(upc);
}
```

Với key gồm nhiều field, khai báo từng argument tương ứng:

```graphql
type StoreProduct @key(fields: "storeId sku") {
  storeId: ID!
  sku: String!
  price: Float!
}
```

```java
@EntityMapping(name = "StoreProduct")
public StoreProduct storeProduct(
        @Argument("storeId") String storeId,
        @Argument("sku") String sku) {
    return storeProductService.findByStoreAndSku(storeId, sku);
}
```

Với key lồng nhau hoặc representation có cấu trúc phức tạp, nhận `Map<String, Object>` rồi bind/kiểm tra cấu trúc rõ ràng. Không giả định key composite là một chuỗi ghép; mỗi field trong field set là một phần của representation.

## Resolve nhiều entity cùng lúc

Gateway thường gửi một danh sách representations tới `_entities`. Nếu nhiều representation cùng thuộc một type, Spring for GraphQL cho phép entity mapping method nhận danh sách ID và trả về danh sách entity tương ứng:

```java
@EntityMapping
public List<Book> book(@Argument List<String> idList) {
    Map<String, Book> booksById = bookService.findAllByIds(idList);

    return idList.stream()
            .map(booksById::get)
            .toList();
}
```

Quy ước tên `idList` giúp Spring suy ra representation field là `id` và bind giá trị từ mỗi representation thành danh sách. Có thể chỉ định tên argument tường minh qua `@Argument` nếu muốn dùng tên tham số khác.

**Thứ tự kết quả phải khớp thứ tự representation đầu vào.** Không trả trực tiếp kết quả `findAllById(...)` nếu repository không bảo đảm thứ tự giống danh sách key. Hãy lập map theo ID rồi dựng lại kết quả theo `idList` như ví dụ.

Phương thức batch cũng có thể trả `Flux<Book>`. Với dữ liệu không đồng bộ, có thể dùng cách này thay cho `List<Book>`. Nếu có representation không thể resolve, hãy xác định rõ cách xử lý và kiểm thử vị trí kết quả tương ứng; không được làm lệch thứ tự các entity còn lại.

## Kết hợp `@EntityMapping` với DataLoader

Khi gateway gửi nhiều representation, một cách khác là resolve từng entity bằng DataLoader. Các lời gọi `load(id)` được gom lại trong cùng GraphQL execution và batch loader tải chúng cùng lúc.

Đăng ký mapped batch loader:

```java
import org.springframework.graphql.execution.BatchLoaderRegistry;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class BookBatchLoaderConfiguration {

    public BookBatchLoaderConfiguration(
            BatchLoaderRegistry registry, BookService bookService) {
        registry.forTypePair(String.class, Book.class)
                .registerMappedBatchLoader((ids, environment) ->
                        Mono.fromSupplier(() -> bookService.findAllByIds(ids)));
    }
}
```

`findAllByIds` trong ví dụ trả `Map<String, Book>` với key là ID. Entity mapping nhận DataLoader và trả kết quả bất đồng bộ:

```java
import java.util.concurrent.CompletableFuture;
import org.dataloader.DataLoader;

@EntityMapping(name = "Book")
public CompletableFuture<Book> book(
        @Argument("id") String id,
        DataLoader<String, Book> dataLoader) {
    return dataLoader.load(id);
}
```

Spring for GraphQL hỗ trợ `DataLoader` như method argument của `@EntityMapping` từ phiên bản 1.4. Với phiên bản cũ hơn, không giả định argument resolver này đã có; cần dùng cách batch mapping được phiên bản đó hỗ trợ hoặc nâng cấp framework.

Chọn giữa list-based entity mapping và DataLoader theo nhu cầu:

- List-based mapping phù hợp khi muốn nhận toàn bộ ID cùng type trong một method và tự tải theo nhóm.
- DataLoader phù hợp khi resolver cần trả về một entity bất đồng bộ theo từng representation, trong khi loader gom các key ở cùng execution.
- Cả hai cách đều cần giữ đúng quan hệ key/entity và tránh truy vấn riêng lẻ cho từng ID.

## Kết hợp `@EntityMapping` với `@SchemaMapping` và `@BatchMapping`

`@EntityMapping` chỉ giải quyết bước lấy entity reference từ representation. Sau đó các field do subgraph đóng góp vẫn được resolve như GraphQL thông thường.

Ví dụ, entity `Book` được tạo từ `id`, còn danh sách review được batch theo nhiều Book:

```java
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.graphql.data.method.annotation.BatchMapping;
import org.springframework.graphql.data.federation.EntityMapping;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.stereotype.Controller;

@Controller
public class ReviewController {

    private final ReviewService reviewService;

    public ReviewController(ReviewService reviewService) {
        this.reviewService = reviewService;
    }

    @EntityMapping
    public Book book(@Argument("id") String id) {
        return new Book(id);
    }

    @BatchMapping(typeName = "Book", field = "reviews")
    public Map<Book, List<Review>> reviews(List<Book> books) {
        Set<String> bookIds = books.stream()
                .map(Book::id)
                .collect(Collectors.toSet());

        Map<String, List<Review>> reviewsByBookId =
                reviewService.findAllByBookIds(bookIds);

        return books.stream().collect(Collectors.toMap(
                book -> book,
                book -> reviewsByBookId.getOrDefault(book.id(), List.of())));
    }
}
```

Entity mapping tạo reference theo từng representation; `@BatchMapping` tải review cho nhiều Book trong một lần batch. Nhờ đó, subgraph không cần gọi review repository một lần cho mỗi entity.

## Xử lý entity không tìm thấy và lỗi representation

Có một số lỗi riêng trong quá trình entity resolution:

| Tình huống | Hành vi |
| --- | --- |
| Representation thiếu `__typename`. | Spring phát sinh `RepresentationException`. |
| Không có `@EntityMapping` tương ứng với typename. | Spring phát sinh `RepresentationException`. |
| Single entity resolver trả `null` hoặc `Mono.empty()`. | Spring phát sinh `RepresentationNotResolvedException`. |
| Service/repository ném exception nghiệp vụ. | Exception có thể được ánh xạ thành GraphQL error. |

Có thể dùng `@GraphQlExceptionHandler` trong cùng controller hoặc `@ControllerAdvice` để chuẩn hóa lỗi từ `@EntityMapping`. Các lỗi được đưa vào response của `_entities` query:

```java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import java.util.Map;
import org.springframework.graphql.data.federation.EntityMapping;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.stereotype.Controller;

@Controller
public class BookEntityController {

    private final BookService bookService;

    public BookEntityController(BookService bookService) {
        this.bookService = bookService;
    }

    @EntityMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(
            GraphqlErrorBuilder<?> builder, BookNotFoundException ex) {
        return builder
                .errorType(ErrorType.NOT_FOUND)
                .message("Không tìm thấy sách")
                .extensions(Map.of("code", "BOOK_NOT_FOUND"))
                .build();
    }
}
```

Trong ví dụ, `bookService` được inject qua constructor như các controller thông thường. Không đưa ID nội bộ, câu SQL hoặc stack trace vào message trả về gateway. Gateway cần nhận mã lỗi và thông tin đủ để xử lý hoặc ghi log; chi tiết triển khai nên nằm ở log nội bộ.

Khi cần biểu diễn entity không tồn tại, hãy chọn chính sách rõ ràng theo contract subgraph và phiên bản Spring for GraphQL đang dùng. Đừng giả định mọi trường hợp `null` đều tự động được chuyển thành phần tử null trong `_entities`; single entity mapping hiện có thể chuyển null/empty thành `RepresentationNotResolvedException`. Với batch mapping, giữ đúng thứ tự và kiểm tra cách biểu diễn phần tử không resolve.

## Bảo mật entity resolution

Representation đến từ Federation gateway, nhưng vẫn phải được xem là input bên ngoài ranh giới trust của service. Key chỉ định danh entity; nó không chứng minh người gọi có quyền đọc entity.

Các nguyên tắc cần áp dụng:

- Xác thực request từ gateway theo cơ chế service-to-service của hệ thống.
- Kiểm tra quyền truy cập và tenant trong service trước khi trả dữ liệu nhạy cảm.
- Không tin `tenantId`, owner hoặc scope chỉ vì chúng xuất hiện trong representation; lấy phạm vi tin cậy từ security context hoặc kiểm tra lại bằng dữ liệu server-side.
- Giới hạn các key field được chấp nhận và validate định dạng trước khi truy vấn.
- Giữ DataLoader/cache trong phạm vi GraphQL request để tránh chia sẻ entity giữa người dùng hoặc tenant.
- Không expose các field nội bộ chỉ vì representation có chứa chúng.

`@EntityMapping` có thể nhận `Principal` hoặc `@AuthenticationPrincipal`. Dù có principal, vẫn cần kiểm tra quyền theo entity ID. Khi dùng DataLoader, batch query phải áp dụng cùng tenant/security scope như truy vấn đơn.

## Kiểm thử `@EntityMapping` bằng GraphQlTester

Có thể kiểm thử trực tiếp `_entities` để xác nhận representation được chuyển thành entity và các field do subgraph cung cấp được resolve đúng. Đây là test ở cấp subgraph; ứng dụng client nghiệp vụ thông thường không cần gọi `_entities`.

```java
import static org.assertj.core.api.Assertions.assertThat;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.ExecutionGraphQlService;
import org.springframework.graphql.test.tester.ExecutionGraphQlServiceTester;

@SpringBootTest
class FederationEntityMappingTests {

    @Autowired
    ExecutionGraphQlService executionGraphQlService;

    @Test
    void resolvesBookRepresentation() {
        ExecutionGraphQlServiceTester tester =
                ExecutionGraphQlServiceTester.create(executionGraphQlService);

        tester.document("""
                query ResolveBook($representations: [_Any!]!) {
                  _entities(representations: $representations) {
                    ... on Book {
                      id
                      reviews {
                        id
                        body
                      }
                    }
                  }
                }
                """)
                .variable("representations", List.of(Map.of(
                        "__typename", "Book",
                        "id", "book-10")))
                .execute()
                .path("_entities[0].id")
                .entity(String.class)
                .isEqualTo("book-10");
    }
}
```

Test giả định subgraph đã bật `FederationSchemaFactory`, schema có `Book @key(fields: "id")`, và `ExecutionGraphQlService` đã được Spring Boot cấu hình. Có thể bổ sung assertion cho `reviews[*].id` để kiểm tra cả bước `@SchemaMapping`/`@BatchMapping` sau khi entity reference được tạo.

Kiểm tra `_service.sdl` để xác nhận subgraph công bố đúng Federation schema:

```java
ExecutionGraphQlServiceTester tester =
        ExecutionGraphQlServiceTester.create(executionGraphQlService);

tester.document("{ _service { sdl } }")
        .execute()
        .path("_service.sdl")
        .entity(String.class)
        .satisfies(sdl -> assertThat(sdl)
                .contains("@key"));
```

Các ca kiểm thử nên có:

- Representation có typename và key hợp lệ.
- Representation thiếu key hoặc thiếu `__typename`.
- Typename không có entity mapping tương ứng.
- Entity tồn tại và entity không tồn tại.
- Composite key được bind đủ field.
- Nhiều representation cùng type được trả theo đúng thứ tự.
- DataLoader được gọi batch thay vì truy vấn riêng cho từng representation.
- Lỗi nghiệp vụ được ánh xạ thành GraphQL error có mã ổn định.
- Quyền truy cập và tenant isolation được áp dụng cho entity lookup.
- `_service.sdl` chứa directive Federation mà gateway cần compose.

## Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `_entities` không tồn tại | Schema chưa dùng `FederationSchemaFactory`. | Khai báo factory bean và schema customizer. |
| `@EntityMapping` không được gọi | Thiếu `@Controller`, typename không khớp hoặc entity mapping không được phát hiện. | Kiểm tra component scan, tên method và `@EntityMapping(name=...)`. |
| Representation không bind được key | Tên `@Argument` không khớp field trong `@key`. | Dùng `@Argument("id")` hoặc nhận full representation map. |
| `RepresentationException` do typename | Representation thiếu `__typename` hoặc không có handler cho type. | Kiểm tra representation và entity type mapping. |
| Entity lookup trả sai bản ghi | Key composite bị bỏ sót field hoặc mapping nhầm key. | Bind đủ mọi field trong `@key` và kiểm tra service lookup. |
| Batch entity trả sai dữ liệu | Kết quả repository không cùng thứ tự với representation. | Dựng lại danh sách theo thứ tự ID đầu vào. |
| Xuất hiện N+1 khi resolve entity/field con | Entity mapping hoặc schema mapping truy vấn riêng từng ID. | Dùng list-based mapping, DataLoader hoặc `@BatchMapping`. |
| Không thấy field mới trong supergraph | SDL subgraph chưa khai báo field/key đúng hoặc composition chưa chạy lại. | Kiểm tra `_service.sdl` và kết quả compose của gateway. |
| Lỗi entity bị lộ chi tiết nội bộ | Exception message được trả nguyên văn. | Chuẩn hóa bằng `@GraphQlExceptionHandler` và giữ chi tiết trong log. |
| Entity được trả dù user không có quyền | Chỉ kiểm tra key tồn tại, không kiểm tra authorization. | Kiểm tra quyền theo principal, tenant và entity trong service. |

## Ghi nhớ

`@EntityMapping` là điểm vào để Spring for GraphQL resolve một Federation entity từ representation do gateway gửi qua `_entities`. Representation chứa `__typename` và các field trong `@key`; method có thể bind từng key bằng `@Argument`, nhận toàn bộ map hoặc nhận danh sách representations. Tên entity mặc định được suy ra từ tên method, hoặc khai báo tường minh bằng `name`/`value`.

Để bật Federation, cấu hình `FederationSchemaFactory` làm schema factory cho `GraphQlSource`. Entity mapping có thể trả entity trực tiếp, kiểu async, danh sách cùng thứ tự hoặc dùng DataLoader để gom tải dữ liệu. Sau bước này, `@SchemaMapping` và `@BatchMapping` tiếp tục resolve field của entity. Kiểm thử `_entities`, `_service`, thứ tự batch, lỗi representation và authorization để bảo đảm subgraph có thể được gateway sử dụng an toàn.

## Tài liệu tham khảo

- [Spring for GraphQL — Federation](https://docs.spring.io/spring-graphql/reference/federation.html)
- [Spring for GraphQL — `@EntityMapping` API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/federation/EntityMapping.html)
- [Spring for GraphQL — `FederationSchemaFactory` API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/federation/FederationSchemaFactory.html)
- [Apollo Federation — Subgraph Specification](https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/reference/subgraph-spec)
- [Apollo Federation — Directives](https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/reference/directives)
