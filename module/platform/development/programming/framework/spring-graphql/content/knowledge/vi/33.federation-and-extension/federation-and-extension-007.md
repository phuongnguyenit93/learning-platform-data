# Resolver cho entity trong Spring for GraphQL Federation

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích entity representation và vai trò của resolver trong một Federation subgraph.
- Hiểu gateway gọi trường _entities như thế nào.
- Cấu hình FederationSchemaFactory trong Spring for GraphQL.
- Dùng @EntityMapping để ánh xạ representation thành entity Java.
- Đọc key bằng @Argument hoặc toàn bộ representation map.
- Phân biệt resolver một entity, resolver theo lô và resolver dùng DataLoader.
- Giữ đúng thứ tự entity khi xử lý nhiều representation.
- Kết hợp @EntityMapping với @SchemaMapping và @BatchMapping.
- Xử lý entity không tồn tại, lỗi và quyền truy cập.
- Kiểm thử entity resolver ở cấp GraphQL subgraph.

## 1. Entity resolver trong Federation là gì?

Trong Apollo Federation, một entity là kiểu GraphQL có thể được nhận diện bằng một hoặc nhiều key. Gateway dùng key để tham chiếu tới cùng một entity khi lập kế hoạch truy vấn qua nhiều subgraph.

Ví dụ, subgraph Catalog sở hữu dữ liệu Book:

~~~graphql
type Book @key(fields: "id") {
    id: ID!
    title: String!
}
~~~

Subgraph Reviews có thể mở rộng kiểu Book để cung cấp các field review:

~~~graphql
type Book @key(fields: "id") @extends {
    id: ID! @external
    reviews: [Review!]!
}

type Review {
    id: ID!
    rating: Int!
    comment: String
}
~~~

Subgraph Reviews không sở hữu Book.title, nhưng cần biết Book nào đang được tham chiếu để tải các review của nó.

Entity resolver nhận representation do Federation gateway gửi tới và chuyển representation đó thành đối tượng Java mà các resolver field còn lại có thể sử dụng.

Trong Spring for GraphQL, method xử lý này được đánh dấu bằng @EntityMapping.

## 2. Representation và key của entity

Một entity representation là một object mô tả entity cần được subgraph phân giải. Nó có trường __typename để xác định GraphQL type và các key field được khai báo bằng directive @key.

Ví dụ representation của Book:

~~~json
{
  "__typename": "Book",
  "id": "book-42"
}
~~~

__typename cho biết representation thuộc entity Book; id là key để tìm hoặc tạo tham chiếu tới Book.

Với key ghép:

~~~graphql
type Product @key(fields: "sku tenantId") {
    sku: ID!
    tenantId: ID!
    name: String!
}
~~~

Representation cần có đủ các key field:

~~~json
{
  "__typename": "Product",
  "sku": "SKU-100",
  "tenantId": "tenant-a"
}
~~~

Entity resolver phải hiểu tất cả key shape mà subgraph công bố. Không giả định mọi representation luôn chỉ có id.

## 3. Gateway gọi _entities như thế nào?

Federation schema có trường _entities để gateway yêu cầu subgraph phân giải một hoặc nhiều entity representation.

Ví dụ operation nội bộ mà gateway có thể gửi tới Reviews subgraph:

~~~graphql
query ResolveEntities($representations: [_Any!]!) {
    _entities(representations: $representations) {
        ... on Book {
            id
            reviews {
                id
                rating
                comment
            }
        }
    }
}
~~~

Variables:

~~~json
{
  "representations": [
    {
      "__typename": "Book",
      "id": "book-42"
    }
  ]
}
~~~

Subgraph nhận danh sách representation, dùng __typename để chọn entity mapping tương ứng, sau đó thực thi các field được yêu cầu trên entity đã phân giải.

Thông thường client ứng dụng gọi gateway, không gọi trực tiếp _entities. Gateway dùng trường này khi query plan cần lấy thêm field từ subgraph khác.

## 4. Bật FederationSchemaFactory

Spring for GraphQL tích hợp thư viện federation-jvm. FederationSchemaFactory tạo GraphQL schema có các thành phần Federation và phát hiện các controller method được đánh dấu @EntityMapping.

Với Spring Boot, khai báo factory và gắn nó vào GraphQlSource:

~~~java
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.data.federation.FederationSchemaFactory;

@Configuration
class FederationConfig {

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

GraphQlSourceBuilderCustomizer yêu cầu Spring Boot dùng FederationSchemaFactory để tạo schema. Nhờ đó các directive và trường Federation như _entities được cấu hình cùng schema của subgraph.

Nếu thiếu bước này, SDL có thể chứa @key nhưng schema runtime chưa được tạo theo Federation. Entity mapping không thể hoạt động chỉ bằng cách thêm annotation @EntityMapping.

## 5. Khai báo SDL cho subgraph

Ví dụ Reviews subgraph mở rộng Book:

~~~graphql
type Book @key(fields: "id") @extends {
    id: ID! @external
    reviews: [Review!]!
}

type Review {
    id: ID!
    rating: Int!
    comment: String
}
~~~

Ý nghĩa:

- @key(fields: "id") xác định key dùng để tham chiếu Book.
- @extends cho biết subgraph đang mở rộng một entity được định nghĩa ở subgraph khác.
- @external đánh dấu id được sở hữu bởi subgraph khác.
- reviews là field do Reviews subgraph cung cấp.

FederationSchemaFactory xử lý các directive Federation khi tạo schema. Với Federation v2, SDL có thể dùng extend schema @link(...) và các directive được import theo Federation version mà hệ thống chọn. Hãy bảo đảm các subgraph và gateway tương thích cùng Federation specification.

## 6. Resolver đơn entity với @EntityMapping

Ví dụ Reviews subgraph chỉ cần tạo một Book reference mang id, sau đó dùng reference này để tải review:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.federation.EntityMapping;
import org.springframework.stereotype.Controller;

@Controller
class BookEntityController {

    @EntityMapping
    public Book book(@Argument String id) {
        return new Book(id);
    }
}
~~~

Spring mặc định suy ra tên entity từ tên method bằng cách viết hoa ký tự đầu: method book ánh xạ tới entity type Book.

Đối số @Argument String id được bind từ key field id trong representation map. Method trả về Book để GraphQL tiếp tục resolve các field được yêu cầu.

Ví dụ domain object:

~~~java
public record Book(String id) {
}
~~~

Trong một subgraph thực tế, entity resolver cũng có thể tải entity đầy đủ từ database hoặc service cục bộ. Việc tạo reference stub phù hợp khi field mà subgraph sở hữu chỉ cần key để truy vấn dữ liệu của chính nó.

## 7. Đặt tên entity rõ ràng

Khi tên method không trùng với quy ước entity type, truyền tên rõ ràng qua @EntityMapping:

~~~java
@Controller
class CatalogEntityController {

    @EntityMapping(name = "Book")
    public Book resolveBook(@Argument String id) {
        return bookService.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }
}
~~~

name chỉ định GraphQL entity type mà method xử lý. Nếu bỏ qua, Spring lấy tên method và viết hoa ký tự đầu để suy ra entity type.

Dùng tên tường minh khi method có tên như resolveBook, loadProduct hoặc findCustomer, để người đọc thấy rõ mapping không phụ thuộc vào tên method.

## 8. Đọc toàn bộ representation map

Ngoài @Argument, entity mapping method có thể nhận toàn bộ representation dưới dạng Map<String, Object>:

~~~java
import java.util.Map;

@EntityMapping(name = "Product")
public Product product(Map<String, Object> representation) {
    String sku = (String) representation.get("sku");
    String tenantId = (String) representation.get("tenantId");

    return productService.findBySkuAndTenant(sku, tenantId)
            .orElseThrow(() -> new ProductNotFoundException(sku));
}
~~~

Cách này hữu ích khi entity có composite key hoặc cần kiểm tra __typename và nhiều thuộc tính trong representation.

Nếu chỉ cần một vài key field đã biết, @Argument thường dễ đọc và có chuyển đổi kiểu rõ ràng hơn.

Không coi các field ngoài key là dữ liệu đáng tin cậy. Gateway có thể gửi các field bổ sung tùy query plan, nhưng identity của entity phải được xác định từ key đã công bố và được xác minh bởi subgraph.

## 9. Các method argument được hỗ trợ

@EntityMapping hỗ trợ nhiều loại method argument để lấy dữ liệu từ representation và GraphQL execution context:

| Argument | Mục đích |
| --- | --- |
| @Argument | Lấy một key hoặc giá trị được bind từ representation |
| Map<String, Object> | Toàn bộ representation của một entity |
| List<Map<String, Object>> | Danh sách representation khi xử lý nhiều entity trong một method |
| @ContextValue | Đọc giá trị từ GraphQL context chính |
| @LocalContextValue | Đọc giá trị từ local GraphQL context |
| GraphQLContext | Truy cập GraphQL context |
| Principal | Lấy principal từ Spring Security context nếu có |
| @AuthenticationPrincipal | Lấy principal của Authentication |
| DataFetchingFieldSelectionSet | Kiểm tra selection set |
| DataLoader<I, E> | Tải entity qua DataLoader |
| DataFetchingEnvironment | Truy cập trực tiếp execution environment |
| Locale | Lấy locale của request |

Các argument context và security cho phép entity resolver áp dụng tenant, locale hoặc quyền truy cập theo người dùng hiện tại. Chúng không làm thay đổi ý nghĩa của key trong representation.

Method có thể trả về entity trực tiếp hoặc các kiểu bất đồng bộ được hỗ trợ như `Mono`, `CompletableFuture` và `Callable`. Chọn kiểu return tương ứng với data access của subgraph; không blocking trong reactive pipeline.

## 10. Xử lý nhiều representation cùng loại

Gateway có thể gửi nhiều representation của cùng entity type trong một lần gọi _entities. Khi cần tải nhiều entity cùng lúc, Spring hỗ trợ method nhận danh sách ID và trả về List hoặc Flux entity.

~~~java
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.federation.EntityMapping;

@EntityMapping
public List<Book> book(@Argument List<String> idList) {
    Map<String, Book> booksById = bookService.findAllByIds(idList)
            .stream()
            .collect(Collectors.toMap(Book::id, Function.identity()));

    return idList.stream()
            .map(id -> {
                Book book = booksById.get(id);
                if (book == null) {
                    throw new BookNotFoundException(id);
                }
                return book;
            })
            .toList();
}
~~~

Quy ước tên idList giúp Spring nhận ra đây là danh sách giá trị của key id. Có thể chỉ định tên argument tường minh qua @Argument nếu cần.

Điểm quan trọng là kết quả phải giữ đúng thứ tự của danh sách representation đầu vào. Không trả về thứ tự database tùy ý vì phần tử thứ nhất trong _entities response phải tương ứng với representation thứ nhất.

Nếu entity có key ghép hoặc representation khác nhau, có thể nhận List<Map<String, Object>> rồi xử lý từng representation theo đúng thứ tự.

## 11. Giữ đúng thứ tự khi batch load

Database thường không bảo đảm thứ tự trả về giống thứ tự của danh sách ID đầu vào. Vì vậy không nên viết:

~~~java
return bookRepository.findAllById(idList);
~~~

rồi giả định kết quả đã đúng thứ tự representation.

Hãy tạo map theo key và tái tạo danh sách theo thứ tự đầu vào:

~~~java
Map<String, Book> booksById = loadedBooks.stream()
        .collect(Collectors.toMap(Book::id, Function.identity()));

List<Book> orderedBooks = idList.stream()
        .map(booksById::get)
        .toList();
~~~

Nếu một key không tìm thấy, hãy quyết định chính sách rõ ràng: biểu diễn entity không phân giải được, trả kết quả null theo semantics được hỗ trợ, hoặc phát sinh lỗi nghiệp vụ. Đừng âm thầm bỏ phần tử vì điều đó làm lệch thứ tự các entity.

Hành vi của entity không tìm thấy có thể phụ thuộc kiểu return và phiên bản Spring for GraphQL. API có RepresentationNotResolvedException cho trường hợp resolver trả null hoặc hoàn tất rỗng; hãy kiểm thử contract này trên phiên bản runtime thay vì giả định Mono.empty() luôn trở thành một phần tử null trong _entities.

## 12. Dùng DataLoader trong @EntityMapping

Khi gateway gửi nhiều representation, DataLoader có thể gom các lần tải entity thành một batch. Spring for GraphQL cho phép nhận DataLoader trực tiếp trong @EntityMapping.

Đăng ký batch loader:

~~~java
import org.springframework.graphql.execution.BatchLoaderRegistry;
import org.springframework.stereotype.Controller;

@Controller
class BookEntityController {

    BookEntityController(
            BatchLoaderRegistry registry,
            BookService bookService) {

        registry.forTypePair(String.class, Book.class)
                .registerBatchLoader((bookIds, environment) ->
                        bookService.findAllByIds(bookIds)
                                .collectMap(Book::id)
                );
    }
}
~~~

Dùng DataLoader trong entity mapping:

~~~java
import java.util.concurrent.CompletableFuture;

import org.dataloader.DataLoader;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.federation.EntityMapping;

@EntityMapping
public CompletableFuture<Book> book(
        @Argument String id,
        DataLoader<String, Book> dataLoader) {

    return dataLoader.load(id);
}
~~~

DataLoader.load(id) trả về một future. Nhiều lần gọi có thể được gom lại để batch loader tải entity theo nhóm thay vì truy vấn từng ID.

Batch loader phải trả kết quả được ánh xạ đúng key. DataLoader quản lý việc phân phối kết quả cho từng lần gọi load, vì vậy map key-value cần chính xác và không được dùng nhầm ID.

## 13. Kết hợp @EntityMapping với @SchemaMapping

@EntityMapping chỉ giải quyết bước tạo entity từ representation. Các field còn lại của entity vẫn có thể được xử lý bằng @SchemaMapping.

Ví dụ Book reference đã được tạo:

~~~java
public record Book(String id) {
}
~~~

Resolver field reviews:

~~~java
import java.util.List;

import org.springframework.graphql.data.method.annotation.SchemaMapping;

@SchemaMapping(typeName = "Book", field = "reviews")
public List<Review> reviews(Book book) {
    return reviewService.findByBookId(book.id());
}
~~~

Luồng xử lý:

1. Gateway gửi representation Book với key id.
2. @EntityMapping trả về đối tượng Book.
3. GraphQL tiếp tục resolve field reviews.
4. @SchemaMapping dùng book.id() để tải review từ dữ liệu cục bộ.

Cách tách này giữ trách nhiệm rõ ràng: entity resolver tạo reference, còn schema mapping xử lý field mà subgraph sở hữu.

## 14. Dùng @BatchMapping cho field của entity

Nếu query yêu cầu reviews cho nhiều Book, resolver @SchemaMapping đơn lẻ có thể tạo N+1 lần truy vấn. Dùng @BatchMapping để tải dữ liệu theo nhóm:

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.graphql.data.method.annotation.BatchMapping;

@BatchMapping(typeName = "Book", field = "reviews")
public Map<Book, List<Review>> reviews(List<Book> books) {
    return reviewService.findReviewsForBooks(books);
}
~~~

@BatchMapping nhận danh sách parent Book và trả map từ từng Book sang danh sách review tương ứng.

Entity resolver và field batch resolver giải quyết hai tầng khác nhau:

- @EntityMapping: phân giải representation thành entity.
- @BatchMapping: tải một field cho nhiều entity parent cùng lúc.

Có thể kết hợp batch entity resolution và batch field resolution để giảm số round trip khi gateway gửi nhiều representation và yêu cầu các field quan hệ.

## 15. Entity có nhiều key hoặc composite key

Một entity có thể khai báo nhiều key hoặc một key gồm nhiều field:

~~~graphql
type Product
    @key(fields: "sku")
    @key(fields: "upc")
{
    sku: ID!
    upc: String!
    name: String!
}
~~~

Hoặc composite key:

~~~graphql
type TenantProduct @key(fields: "tenantId productId") {
    tenantId: ID!
    productId: ID!
    name: String!
}
~~~

Entity resolver phải phân giải được các representation theo key mà gateway sử dụng. Với composite key, nhận các field riêng biệt:

~~~java
@EntityMapping(name = "TenantProduct")
public TenantProduct tenantProduct(
        @Argument String tenantId,
        @Argument String productId) {

    return productService.find(tenantId, productId)
            .orElseThrow(() ->
                    new ProductNotFoundException(productId)
            );
}
~~~

Khi có nhiều @key, cần kiểm thử từng key shape. Không giả định gateway luôn chọn key đầu tiên trong SDL; query planner có thể dùng key phù hợp với dữ liệu đang có từ subgraph khác.

## 16. Xử lý entity không tồn tại và exception

Entity resolver có thể không tìm thấy entity do dữ liệu đã bị xóa, key không hợp lệ hoặc subgraph không có quyền phân giải representation.

Không nên trả một object rỗng với ID giả vì gateway sẽ coi đó là entity hợp lệ và các field tiếp theo có thể trả dữ liệu sai.

Có thể ném exception nghiệp vụ và ánh xạ nó thành GraphQL error:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;

import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;

@GraphQlExceptionHandler
public GraphQLError handleBookNotFound(BookNotFoundException exception) {
    return GraphqlErrorBuilder.newError()
            .message("Không tìm thấy Book được yêu cầu.")
            .build();
}
~~~

@GraphQlExceptionHandler có thể đặt trong controller chứa @EntityMapping hoặc trong @ControllerAdvice. Spring for GraphQL đưa lỗi được ánh xạ vào response của _entities query.

Không trả stack trace, SQL, tên bảng hoặc thông tin nội bộ trong error message. Hãy ghi diagnostics ở server log có kiểm soát và trả thông điệp phù hợp với contract công khai.

## 17. Bảo vệ entity resolver

Representation được gửi từ gateway nhưng vẫn là dữ liệu đầu vào của subgraph. Không nên coi việc request đi qua gateway là bằng chứng rằng người dùng có quyền truy cập mọi entity.

Các kiểm tra quan trọng:

- Xác thực người dùng theo cơ chế Spring Security.
- Kiểm tra entity thuộc tenant hiện tại.
- Kiểm tra quyền đọc entity trước khi trả reference hoặc dữ liệu.
- Không tin tenantId, ownerId hoặc role chỉ vì chúng nằm trong representation.
- Không trả các field nội bộ chỉ vì gateway yêu cầu.
- Kiểm tra quyền ở subgraph, đặc biệt nếu subgraph có thể được gọi trực tiếp trong mạng nội bộ.

Ví dụ truyền principal vào entity resolver:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;

@EntityMapping
public Book book(
        @Argument String id,
        @AuthenticationPrincipal AppPrincipal principal) {

    return bookService.findVisibleBook(id, principal.tenantId())
            .orElseThrow(() -> new BookNotFoundException(id));
}
~~~

Ở đây tenant được lấy từ principal đã xác thực. Representation chỉ cung cấp key id; service tự kiểm tra entity có thuộc tenant đó hay không.

Nếu authorization phụ thuộc field cụ thể, tiếp tục bảo vệ @SchemaMapping hoặc service mà field resolver gọi. Entity đã được phân giải không có nghĩa mọi field của entity đều được phép truy cập.

## 18. Kiểm thử entity resolver

Có thể kiểm thử _entities trực tiếp qua GraphQL tester sau khi cấu hình Federation schema và controller.

Ví dụ:

~~~java
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.graphql.test.tester.HttpGraphQlTester;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class BookEntityMappingTests {

    @LocalServerPort
    int port;

    HttpGraphQlTester graphQlTester;

    @BeforeEach
    void setUp() {
        WebTestClient webTestClient = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .build();

        graphQlTester = HttpGraphQlTester.create(webTestClient);
    }

    @Test
    void shouldResolveBookRepresentation() {
        var response = graphQlTester.document("""
                query ResolveBook($representations: [_Any!]!) {
                    _entities(representations: $representations) {
                        ... on Book {
                            id
                            reviews {
                                id
                            }
                        }
                    }
                }
                """)
                .variable("representations", List.of(
                        Map.of(
                                "__typename", "Book",
                                "id", "book-42"
                        ),
                        Map.of(
                                "__typename", "Book",
                                "id", "book-99"
                        )
                ))
                .execute();

        response.path("_entities[0].id")
                .entity(String.class)
                .isEqualTo("book-42");

        response.path("_entities[1].id")
                .entity(String.class)
                .isEqualTo("book-99");
    }
}
~~~

Test cần chạy với Federation schema đã được bật. Nếu ứng dụng dùng HTTP endpoint thật, có thể dùng HttpGraphQlTester; nếu chỉ cần kiểm tra web GraphQL handler, dùng tester tương ứng với handler của ứng dụng.

Nên kiểm thử thêm:

- Representation có __typename và key hợp lệ.
- Representation thiếu key.
- Entity type không có mapping.
- Composite key và từng key alternative.
- Nhiều representation cùng type và thứ tự kết quả.
- Batch loader nhận nhiều ID và phân phối đúng entity.
- Entity không tồn tại.
- Exception được chuyển thành GraphQL error.
- Principal thuộc tenant khác bị từ chối.
- Field resolver và batch resolver tải đúng dữ liệu cục bộ.

## 19. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| _entities không tồn tại | Schema chưa được tạo bằng FederationSchemaFactory | Đăng ký factory và schema customizer |
| Không tìm thấy entity mapping | Tên method không khớp entity type hoặc thiếu name | Dùng tên method đúng quy ước hoặc @EntityMapping(name = "...") |
| Key nhận được là null | Representation thiếu key hoặc @Argument sai tên | Kiểm tra @key và tên argument |
| Resolver không đọc được composite key | Method chỉ nhận một key field | Bind đầy đủ các key field hoặc đọc representation map |
| Kết quả batch sai entity | Danh sách trả về không giữ thứ tự representation | Tái tạo kết quả theo thứ tự ID đầu vào |
| Batch loader trả nhầm entity | Map key-value không chính xác | Dùng entity key làm map key và kiểm thử từng ID |
| DataLoader vẫn gọi từng query | Loader chưa được đăng ký hoặc key type không khớp | Kiểm tra forTypePair và argument DataLoader |
| Entity resolver chạy nhưng field không có dữ liệu | Chưa có @SchemaMapping hoặc @BatchMapping cho field mở rộng | Bổ sung field resolver của subgraph |
| Entity không tồn tại tạo response khó hiểu | Chưa định nghĩa missing-entity/error policy | Ánh xạ exception và kiểm thử _entities response |
| Người dùng đọc được entity tenant khác | Chỉ tin gateway hoặc key trong representation | Kiểm tra quyền ở subgraph/service |
| Federation directive bị báo lỗi SDL | Gateway và subgraph không thống nhất Federation version/directives | Kiểm tra @link, @extends, @external và schema factory |

## 20. Quy trình triển khai entity resolver

Khi thêm một entity vào Federation subgraph, hãy thực hiện theo trình tự:

1. **Xác định entity và key.** Chọn @key ổn định, duy nhất và có thể phân giải từ subgraph.
2. **Khai báo SDL.** Dùng entity type hoặc extend type cùng các directive Federation phù hợp.
3. **Bật Federation schema.** Đăng ký FederationSchemaFactory với GraphQlSource.
4. **Viết @EntityMapping.** Bind key bằng @Argument hoặc representation map.
5. **Chọn cách tải.** Dùng resolver đơn, resolver theo lô hoặc DataLoader.
6. **Giữ thứ tự representation.** Đảm bảo kết quả batch tương ứng đúng thứ tự đầu vào.
7. **Viết field resolver.** Dùng @SchemaMapping hoặc @BatchMapping cho các field subgraph sở hữu.
8. **Bảo vệ dữ liệu.** Xác thực principal, tenant và quyền truy cập entity.
9. **Chuẩn hóa lỗi.** Xử lý entity không tồn tại và exception theo GraphQL contract.
10. **Kiểm thử _entities.** Bao phủ key, batch, order, error và authorization trước khi tích hợp gateway.

## 21. Tổng kết

@EntityMapping là điểm vào để Spring for GraphQL phân giải entity representation do Federation gateway gửi qua _entities. Spring bind key từ representation vào method argument, sau đó method trả về entity để GraphQL tiếp tục xử lý các field còn lại.

FederationSchemaFactory phải được gắn vào GraphQlSource để tạo Federation schema và phát hiện entity mappings. Với nhiều representation, có thể nhận danh sách key và trả List hoặc Flux theo đúng thứ tự đầu vào; DataLoader là lựa chọn khác để gom các lần tải entity. Dùng @SchemaMapping và @BatchMapping cho các field mà subgraph sở hữu, đồng thời kiểm tra tenant, quyền truy cập và lỗi entity không tồn tại. Kiểm thử trực tiếp _entities giúp xác minh mapping hoạt động trước khi đưa subgraph vào gateway.

## Tài liệu tham khảo

- [Spring for GraphQL – Federation](https://docs.spring.io/spring-graphql/reference/federation.html)
- [Spring for GraphQL – EntityMapping API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/federation/EntityMapping.html)
- [Apollo Federation – Entities](https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/entities)
- [Apollo Federation – Subgraph Specification](https://www.apollographql.com/docs/federation/subgraph-spec)

