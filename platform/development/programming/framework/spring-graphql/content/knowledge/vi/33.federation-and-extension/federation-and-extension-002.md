# FederationSchemaFactory

Apollo Federation cho phép nhiều GraphQL subgraph cùng công bố một phần của đồ thị dữ liệu. Gateway kết hợp schema của các subgraph thành một supergraph, sau đó phân rã query của client thành các request gửi đến những service phù hợp.

Trong Spring for GraphQL, FederationSchemaFactory là thành phần tích hợp với thư viện federation-jvm để khởi tạo GraphQL schema theo giao thức subgraph. Factory chuyển TypeDefinitionRegistry và RuntimeWiring thành GraphQLSchema có các thành phần federation cần thiết, đồng thời phát hiện các controller method được đánh dấu @EntityMapping để phân giải entity khi gateway gọi _entities.

Điểm quan trọng là FederationSchemaFactory không phải gateway và cũng không tự viết truy vấn dữ liệu nghiệp vụ. Nó chuẩn bị schema federation và kết nối entity representation của gateway với controller method trong subgraph. Ứng dụng vẫn phải khai báo SDL, triển khai entity lookup, bảo vệ dữ liệu và kiểm thử giao thức.

## 1. FederationSchemaFactory giải quyết vấn đề gì?

Một GraphQL service thông thường có thể xử lý query bắt đầu từ root field như books hoặc authors. Trong Federation, gateway có thể cần lấy một entity từ subgraph khác rồi yêu cầu subgraph hiện tại bổ sung field thuộc trách nhiệm của nó.

Ví dụ:

- Catalog subgraph sở hữu Book gồm id, title và price.
- Review subgraph mở rộng Book bằng reviews và rating.
- Gateway nhận query có cả title và reviews.
- Gateway gọi Catalog để lấy Book, sau đó gọi Review để resolve các Book entity dựa trên key.

Review subgraph cần hiểu representation của Book, tìm lại dữ liệu hoặc ngữ cảnh tương ứng, rồi trả các field mà nó sở hữu. Apollo Federation chuẩn hóa bước này qua entity key và field _entities.

FederationSchemaFactory giúp Spring for GraphQL chuẩn bị schema và entity data fetcher cho luồng đó. Ứng dụng chỉ cần khai báo entity mapping bằng @EntityMapping thay vì tự viết DataFetcher cho trường _entities và type resolver của từng entity.

## 2. Các khái niệm liên quan

| Khái niệm | Vai trò |
| --- | --- |
| Supergraph | Schema tổng hợp mà client sử dụng |
| Subgraph | Một GraphQL service sở hữu hoặc mở rộng một phần schema |
| Federation gateway/router | Thành phần nhận query từ client và lập query plan gọi các subgraph |
| Entity | Object có thể được nhận diện giữa các subgraph bằng key |
| @key | Directive khai báo tập field dùng để nhận diện entity |
| Representation | Object gateway gửi cho subgraph, thường có __typename và các key field |
| _entities | Root field dùng để resolve một danh sách entity representation |
| _service | Root field cung cấp SDL của subgraph cho quá trình composition |
| FederationSchemaFactory | Factory tạo schema federation và kết nối entity mapping trong Spring |
| @EntityMapping | Annotation đánh dấu method tải entity từ representation |

Một subgraph có thể sở hữu entity hoặc chỉ mở rộng entity do subgraph khác sở hữu. Quyền sở hữu field và entity key phải được thiết kế rõ trong Federation SDL.

## 3. Vị trí của FederationSchemaFactory trong kiến trúc

Luồng khởi tạo và thực thi có thể hình dung:

~~~mermaid
flowchart TD
    A[SDL resources] --> C[GraphQlSource.Builder]
    B[RuntimeWiringConfigurer] --> C
    D[FederationSchemaFactory] --> C
    C --> E[GraphQLSchema của subgraph]
    E --> F[_service và _entities]
    E --> G[EntityMapping DataFetchers]
    H[Federation Gateway] --> I[Query plan]
    I --> J[Subgraph endpoint]
    J --> K[_entities representations]
    K --> G
    G --> L[Entity instances]
    L --> M[SchemaMapping và BatchMapping]
    M --> N[Entity fields trong response]
~~~

Factory tham gia lúc GraphQlSource tạo GraphQLSchema. Khi request đến, GraphQL execution dùng schema đã tạo để thực thi query bình thường hoặc entity resolution từ gateway.

FederationSchemaFactory không điều phối request giữa các service, không thay gateway và không tự composition schema thành supergraph. Những trách nhiệm đó thuộc federation router/gateway và công cụ composition.

## 4. Cấu hình FederationSchemaFactory

Theo cấu hình Spring Boot, khai báo FederationSchemaFactory thành bean và đăng ký schema factory callback trên GraphQlSourceBuilderCustomizer:

~~~java
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.data.federation.FederationSchemaFactory;

@Configuration
public class FederationConfig {

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

Trong cấu hình này:

1. Spring tạo FederationSchemaFactory như một bean.
2. Factory được Spring quản lý application context và phát hiện các controller method có @EntityMapping.
3. GraphQlSourceBuilderCustomizer yêu cầu GraphQlSource.Builder dùng factory::createGraphQLSchema.
4. Khi schema được tạo, factory dùng federation-jvm để biến schema registry/runtime wiring thành schema federation.

Không tạo factory bằng new bên trong callback nếu muốn factory phát hiện controller trong Spring application context. Khai báo bean giúp lifecycle và controller detection được thiết lập đúng.

GraphQlSourceBuilderCustomizer thuộc Spring Boot GraphQL auto-configuration. Nếu không dùng Spring Boot, cần tự cấu hình GraphQlSource.Builder và truyền schema factory callback vào builder tương ứng.

## 5. FederationSchemaFactory hoạt động ở bước schema creation

GraphQlSource mặc định dùng GraphQL Java SchemaGenerator để tạo GraphQLSchema từ type definitions và RuntimeWiring. Khi tích hợp federation, schema cần được xử lý thêm để hiểu federation directives và entity resolution.

FederationSchemaFactory cung cấp hai phương thức đáng chú ý:

| Phương thức | Mục đích |
| --- | --- |
| createGraphQLSchema(registry, wiring) | Tạo GraphQLSchema hoàn chỉnh cho subgraph |
| createSchemaTransformer(registry, wiring) | Tạo SchemaTransformer để ứng dụng có thể cấu hình thêm trước khi build schema |

createGraphQLSchema thiết lập _entities DataFetcher và TypeResolver cho federated types thông qua SchemaTransformer. Federation schema transformation cũng cung cấp các thành phần subgraph protocol cần thiết như _service để gateway có thể lấy SDL.

Trong đa số ứng dụng, callback factory::createGraphQLSchema là đủ. Chỉ dùng createSchemaTransformer khi cần gọi thêm API của federation SchemaTransformer trước khi hoàn tất schema.

## 6. Federation SDL và entity key

Một entity cần có key để gateway có thể tham chiếu nó giữa các subgraph. Ví dụ Book được nhận diện bằng id:

~~~graphql
type Book @key(fields: "id") {
    id: ID!
    title: String!
    price: Float
}
~~~

Nếu subgraph khác mở rộng Book, schema của subgraph đó có thể khai báo phần mở rộng:

~~~graphql
type Book @key(fields: "id") @extends {
    id: ID! @external
    author: Author
}

type Author {
    id: ID!
    name: String!
}
~~~

Ví dụ trên minh họa cú pháp Federation có @extends và @external. Cú pháp chính xác phụ thuộc phiên bản Apollo Federation mà subgraph sử dụng. Federation 2 có cơ chế @link và cách khai báo directive khác; không trộn SDL của Federation 1 với Federation 2 tùy tiện.

@key(fields: "id") cho biết gateway có thể định danh Book bằng field id. @external cho biết field đó được khai báo ở subgraph khác và được tham chiếu trong subgraph mở rộng. Subgraph hiện tại có thể bổ sung field author mà không cần sở hữu lại title hoặc price.

Một entity có thể có nhiều key hoặc key gồm nhiều field. Với composite key, representation sẽ chứa toàn bộ field cần thiết để phân giải entity. Entity mapping phải đọc đúng các field đó.

## 7. Federation directives và vai trò của factory

Federation SDL có thể sử dụng các directive như:

| Directive | Ý nghĩa khái quát |
| --- | --- |
| @key | Khai báo field set định danh entity |
| @extends | Đánh dấu type được mở rộng từ subgraph khác trong cú pháp Federation tương ứng |
| @external | Field được định nghĩa bởi subgraph khác |
| @requires | Field hiện tại cần thêm field từ entity representation |
| @provides | Khai báo field được cung cấp qua một quan hệ cụ thể |
| @shareable | Cho phép nhiều subgraph cùng resolve field theo quy tắc Federation 2 |
| @override | Chuyển quyền resolve field từ subgraph này sang subgraph khác theo Federation 2 |

FederationSchemaFactory không quyết định ownership của field thay cho ứng dụng. Factory dùng schema và federation directives để tạo subgraph schema; gateway composition vẫn phải kiểm tra các directive có hợp lệ và các subgraph có nhất quán hay không.

Chỉ khai báo directive mà không triển khai entity resolver phù hợp vẫn chưa đủ để gateway truy cập entity. Ngược lại, có @EntityMapping nhưng schema không có entity key phù hợp thì gateway không thể tạo representation đúng.

## 8. _service và _entities

Federation subgraph có các field dành cho giao thức:

- _service { sdl }: trả SDL của subgraph để gateway hoặc công cụ composition đọc.
- _entities(representations: ...): nhận các representation và trả entity tương ứng.

Ví dụ query lấy SDL:

~~~graphql
query {
    _service {
        sdl
    }
}
~~~

Ví dụ entity query:

~~~graphql
query ResolveBook {
    _entities(
        representations: [
            { __typename: "Book", id: "book-01" }
        ]
    ) {
        ... on Book {
            id
            title
            author {
                id
                name
            }
        }
    }
}
~~~

Mỗi representation có __typename để xác định GraphQL entity type và các field thuộc key. Gateway có thể gửi nhiều representation trong cùng một lần gọi _entities, bao gồm nhiều entity type nếu schema có nhiều entity.

_entities trả về danh sách các entity tương ứng với representation. Vì kết quả có thể chứa nhiều kiểu entity, GraphQL client thường dùng inline fragment để chọn field theo từng type.

## 9. @EntityMapping kết nối representation với Java object

@EntityMapping đánh dấu controller method dùng để tải entity từ representation:

~~~java
@Controller
public class BookFederationController {

    private final BookService bookService;

    public BookFederationController(BookService bookService) {
        this.bookService = bookService;
    }

    @EntityMapping
    public Book book(@Argument String id) {
        return bookService.findById(id);
    }

    @SchemaMapping
    public Author author(Book book) {
        return bookService.findAuthor(book);
    }
}
~~~

Với tên method book, tên entity mặc định được suy ra thành Book. Có thể khai báo tên rõ ràng khi method name không trùng với entity type:

~~~java
@EntityMapping(name = "Book")
public Book resolveBook(@Argument String id) {
    return bookService.findById(id);
}
~~~

@EntityMapping không thay thế @SchemaMapping. Nó xử lý bước khôi phục entity từ representation; các field còn lại của entity vẫn có thể dùng @SchemaMapping, @BatchMapping hoặc DataLoader như GraphQL thông thường.

## 10. @Argument được lấy từ representation

Khi gateway gửi:

~~~json
{
  "__typename": "Book",
  "id": "book-01"
}
~~~

Spring for GraphQL lấy representation map và bind field id vào tham số:

~~~java
@EntityMapping
public Book book(@Argument("id") String bookId) {
    return bookService.findById(bookId);
}
~~~

Tên trong @Argument là key của representation. Giá trị được chuyển đổi sang kiểu Java theo cơ chế argument binding của Spring for GraphQL.

Nếu entity dùng composite key hoặc cần kiểm tra thêm metadata, method có thể nhận toàn bộ Map:

~~~java
@EntityMapping(name = "Book")
public Book book(Map<String, Object> representation) {
    String tenantCode = (String) representation.get("tenantCode");
    String isbn = (String) representation.get("isbn");
    return bookService.findByTenantAndIsbn(tenantCode, isbn);
}
~~~

Representation map có thể chứa __typename và các key field. Không tin các giá trị đó như thông tin xác thực; chúng chỉ định danh đối tượng để resolver tra cứu. Authorization vẫn phải dựa trên principal và policy của service.

## 11. Các kiểu tham số được hỗ trợ

Entity mapping method hỗ trợ nhiều loại tham số:

| Tham số | Mục đích |
| --- | --- |
| @Argument | Đọc một giá trị có tên từ representation và bind sang kiểu Java |
| Map<String, Object> | Đọc toàn bộ representation của một entity |
| List<Map<String, Object>> | Đọc nhiều representation trong một entity mapping method |
| @ContextValue | Lấy giá trị từ GraphQLContext |
| @LocalContextValue | Lấy giá trị từ local GraphQLContext |
| GraphQLContext | Truy cập context của DataFetchingEnvironment |
| Principal hoặc @AuthenticationPrincipal | Truy cập principal đã xác thực nếu Spring Security được tích hợp |
| DataFetchingEnvironment | Truy cập execution context ở mức thấp |
| DataFetchingFieldSelectionSet | Kiểm tra selection set của entity query |
| DataLoader<I, E> | Tải entity thông qua DataLoader |
| Locale | Lấy locale của request |

Method có thể trả entity trực tiếp hoặc kiểu async/reactive được hỗ trợ như Mono, CompletableFuture và Callable. Chọn return type phù hợp với execution model của ứng dụng; không block event-loop khi dùng reactive transport.

## 12. EntityMapping cho nhiều representation

Gateway có thể gửi nhiều Book representation cùng lúc. Spring for GraphQL hỗ trợ entity mapping nhận danh sách ID và trả danh sách entity:

~~~java
@Controller
public class BookFederationController {

    private final BookService bookService;

    public BookFederationController(BookService bookService) {
        this.bookService = bookService;
    }

    @EntityMapping
    public List<Book> book(@Argument List<String> idList) {
        return bookService.findAllInOrder(idList);
    }
}
~~~

Tên tham số idList giúp Spring nhận diện đây là danh sách giá trị id từ nhiều representation. Quy ước de-pluralize loại bỏ phần hậu tố List để tìm tên key tương ứng. Có thể khai báo tên argument tường minh nếu cần.

Khi trả về List hoặc Flux cho batch entity mapping, thứ tự entity phải tương ứng với thứ tự representation đầu vào. Không chỉ trả về một tập hợp không có thứ tự; nếu repository trả kết quả theo thứ tự khác, cần sắp xếp lại theo danh sách ID ban đầu.

Nếu cần xử lý từng representation phức tạp, có thể nhận List<Map<String, Object>> rồi trả kết quả theo đúng thứ tự. Cách này hữu ích với composite key hoặc khi representation có metadata bổ sung.

## 13. Kết hợp DataLoader để tải federated entity

Nếu mỗi representation chỉ chứa một ID và muốn gom các lần tải entity theo batch, có thể dùng DataLoader:

~~~java
@Controller
public class BookFederationController {

    @EntityMapping
    public CompletableFuture<Book> book(
            @Argument String id,
            DataLoader<String, Book> bookLoader) {

        return bookLoader.load(id);
    }
}
~~~

Đăng ký batch loader qua BatchLoaderRegistry:

~~~java
@Component
public class BookBatchLoader {

    public BookBatchLoader(
            BatchLoaderRegistry registry,
            BookService bookService) {

        registry.forTypePair(String.class, Book.class)
            .registerMappedBatchLoader((ids, environment) ->
                Mono.fromCallable(() -> bookService.findMapped(ids)));
    }
}
~~~

Trong ví dụ, bookService.findMapped(ids) trả Map từ ID sang Book. DataLoader gom các lần load trong cùng GraphQL execution và dispatch batch theo lifecycle của GraphQL Java.

DataLoader cache cần được cô lập theo execution/request. Không chia sẻ cache entity giữa user hoặc tenant nếu kết quả phụ thuộc quyền truy cập. Nếu batch loader dùng JPA blocking trong WebFlux, cần chạy trên scheduler phù hợp và đặt transaction ở service thực hiện batch.

## 14. Kết hợp @BatchMapping cho field mở rộng

Sau khi entity được khôi phục, các nested field có thể dùng @BatchMapping:

~~~java
@Controller
public class BookFieldController {

    private final AuthorService authorService;

    public BookFieldController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(List<Book> books) {
        return authorService.findByBooks(books);
    }
}
~~~

Luồng này tách hai nhiệm vụ:

1. @EntityMapping tìm các Book theo representation từ gateway.
2. @BatchMapping tải Author cho nhiều Book trong cùng một batch.

Kết hợp entity resolution và batch field mapping giúp subgraph xử lý nhiều entity hiệu quả hơn, tránh một query cho mỗi representation và một query cho mỗi nested field.

## 15. TypeResolver và tên Java class

FederationSchemaFactory cần ánh xạ Java entity object về GraphQL entity type. Mặc định, factory sử dụng ClassNameTypeResolver.

Nếu Java class có tên Book nhưng GraphQL type cũng là Book, mapping mặc định thường phù hợp. Nếu Java class có tên CatalogBook nhưng GraphQL type là Book, hoặc có hierarchy nhiều entity type, cần cấu hình TypeResolver tường minh:

~~~java
@Bean
FederationSchemaFactory federationSchemaFactory() {
    FederationSchemaFactory factory = new FederationSchemaFactory();
    factory.setTypeResolver(environment -> {
        Object object = environment.getObject();
        if (object instanceof CatalogBook) {
            return environment.getSchema().getObjectType("Book");
        }
        return null;
    });
    return factory;
}
~~~

TypeResolver cần trả GraphQL object type phù hợp với entity instance. Ví dụ trên minh họa ý tưởng cho một class cụ thể; trong ứng dụng thực tế, cần xử lý tất cả entity type được factory quản lý và có fallback rõ ràng.

Không cấu hình custom resolver nếu ClassNameTypeResolver đã đáp ứng. Cấu hình sai có thể khiến _entities không xác định được kiểu của object trả về hoặc lỗi khi serialize entity response.

Method setTypeResolver có thể khác nhau theo phiên bản Spring for GraphQL. Nếu dùng nhánh cũ không có method này, cần kiểm tra API đúng phiên bản hoặc tùy chỉnh SchemaTransformer theo khả năng được cung cấp; không sao chép nguyên cấu hình từ tài liệu phiên bản mới.

## 16. Xử lý lỗi trong @EntityMapping

Entity mapping có thể gặp các lỗi như:

- Representation thiếu __typename.
- Representation không có key cần thiết.
- Entity không tồn tại.
- Người dùng không có quyền truy cập entity.
- Service/repository gặp lỗi hạ tầng.

Spring for GraphQL có RepresentationException cho trường hợp representation thiếu thông tin cần thiết và RepresentationNotResolvedException khi resolver trả null hoặc hoàn tất rỗng trong tình huống entity không được phân giải.

Có thể dùng @GraphQlExceptionHandler để chuyển exception từ @EntityMapping thành GraphQLError:

~~~java
@Controller
public class BookFederationController {

    @EntityMapping
    public Book book(@Argument String id) {
        return bookService.findById(id);
    }

    @GraphQlExceptionHandler
    public GraphQLError handleNotFound(
            BookNotFoundException exception,
            GraphqlErrorBuilder<?> builder) {

        return builder
            .errorType(ErrorType.NOT_FOUND)
            .message("Book not found")
            .build();
    }
}
~~~

Exception handler có thể đặt trong cùng controller hoặc @ControllerAdvice. Error sẽ xuất hiện trong response của query _entities. Message gửi client không nên chứa SQL, stack trace, token hoặc thông tin nội bộ.

## 17. Bảo mật entity resolution

Representation do gateway gửi không phải bằng chứng rằng caller được phép truy cập entity. Mỗi subgraph vẫn cần thực hiện authorization:

- Xác thực request đến subgraph theo cơ chế tin cậy giữa gateway và service.
- Lấy principal/tenant từ security context hoặc GraphQLContext.
- Kiểm tra caller có quyền đọc entity được yêu cầu hay không.
- Không tin tenantId, ownerId hoặc role chỉ vì representation chứa chúng.
- Không trả dữ liệu field thuộc service khác nếu caller không có quyền.
- Áp dụng authorization cả trong batch loader, không chỉ trong resolver đơn lẻ.

Ví dụ:

~~~java
@EntityMapping
public Book book(
        @Argument String id,
        Principal principal) {

    return bookService.findVisibleTo(id, principal.getName());
}
~~~

Nếu gateway dùng service credential chung, subgraph cần biết cách truyền end-user identity hoặc authorization context theo kiến trúc đã chọn. Chỉ xác thực gateway không tự động chứng minh user cuối có quyền với mọi entity.

## 18. Kiểm tra schema federation sau khi khởi tạo

Sau khi cấu hình factory, có thể kiểm tra _service.sdl:

~~~graphql
query {
    _service {
        sdl
    }
}
~~~

SDL trả về cần chứa entity type và federation directive tương ứng. Đây là cách nhanh để xác minh subgraph schema đã được tạo với federation support.

Có thể kiểm tra _entities:

~~~graphql
query {
    _entities(
        representations: [
            { __typename: "Book", id: "book-01" }
        ]
    ) {
        ... on Book {
            id
            title
        }
    }
}
~~~

Nếu _service hoặc _entities không tồn tại, kiểm tra schemaFactory callback có được gắn vào GraphQlSource.Builder hay không. Nếu _entities tồn tại nhưng entity không resolve, kiểm tra @EntityMapping, key field và representation.

## 19. Kiểm thử bằng GraphQlTester

Test _entities ở mức GraphQL execution có thể dùng GraphQlTester:

~~~java
@SpringBootTest
class FederationGraphQlTests {

    @Autowired
    GraphQlService graphQlService;

    GraphQlTester graphQlTester;

    @BeforeEach
    void setUp() {
        graphQlTester =
            ExecutionGraphQlServiceTester.create(graphQlService);
    }

    @Test
    void resolvesBookRepresentation() {
        var response = graphQlTester.document("""
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
                    "id", "book-01")))
            .execute();

        response.errors().verify();
        response.path("_entities[0].id")
            .entity(String.class)
            .isEqualTo("book-01");
    }
}
~~~

Kiểm thử _service:

~~~java
var response = graphQlTester.document("""
        query {
            _service {
                sdl
            }
        }
        """)
    .execute();

response.errors().verify();
response.path("_service.sdl")
    .entity(String.class)
    .satisfies(sdl -> {
        assertThat(sdl).contains("@key");
        assertThat(sdl).contains("type Book");
    });
~~~

Các test trên xác nhận GraphQL service có federation fields và entity mapping hoạt động. Để kiểm tra toàn bộ Federation composition, cần thêm test hoặc pipeline chạy công cụ composition với SDL của tất cả subgraph; GraphQlTester đơn lẻ không xác minh được supergraph.

## 20. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không có _entities | Chưa cấu hình FederationSchemaFactory làm schema factory | Kiểm tra bean và GraphQlSourceBuilderCustomizer |
| Không có _service | Schema chưa được tạo qua federation transformation hoặc cấu hình không đúng | Kiểm tra factory callback và SDL federation |
| @EntityMapping không được gọi | Controller chưa được phát hiện hoặc type name không khớp | Đăng ký factory thành bean, kiểm tra method và entity name |
| Không bind được id | Representation thiếu key hoặc @Argument sai tên | So sánh @key với field trong representation |
| Resolver trả entity nhưng GraphQL báo không xác định type | Java object không ánh xạ được sang GraphQL entity type | Kiểm tra ClassNameTypeResolver hoặc setTypeResolver |
| Một số representation bị thiếu kết quả | Batch result không giữ thứ tự hoặc thiếu entity | Trả kết quả đúng thứ tự representation hoặc dùng mapped result phù hợp |
| _entities trả lỗi cho entity | Resolver ném exception hoặc không tìm thấy entity | Kiểm tra GraphQlExceptionHandler và error contract |
| Gateway composition thất bại | Directive/key giữa các subgraph không nhất quán | Kiểm tra Federation version, @key, @external, @extends và ownership |
| Hoạt động local nhưng gateway không gọi được | Endpoint, auth hoặc subgraph registration sai | Kiểm tra router config, network và service authentication |
| Batch loader lộ dữ liệu chéo tenant | Cache hoặc batch query không có authorization scope | Cô lập DataLoader theo request và áp dụng tenant predicate |

## 21. Lưu ý tương thích phiên bản

FederationSchemaFactory được Spring for GraphQL cung cấp từ phiên bản 1.3.0. API hiện hành nằm trong package org.springframework.graphql.data.federation. Khi dùng Spring Boot, nên để dependency management của Spring Boot quản lý phiên bản Spring for GraphQL và GraphQL Java tương thích.

FederationSchemaFactory tích hợp với federation-jvm. Không tự nâng federation-jvm hoặc GraphQL Java độc lập nếu chưa kiểm tra compatibility với phiên bản Spring for GraphQL đang dùng.

Directive và SDL phụ thuộc Apollo Federation version. Federation 1 thường gặp @extends và @external; Federation 2 sử dụng schema @link để import federation directives và có thêm directive như @shareable hoặc @override. Hãy bảo đảm gateway, composition tool và federation-jvm cùng hỗ trợ phiên bản SDL đã chọn.

Nếu cần tùy chỉnh schema transformation sâu hơn, kiểm tra API createSchemaTransformer của đúng phiên bản. Không sao chép constructor hoặc method từ tài liệu của một phiên bản khác khi dependency dự án chưa được xác nhận.

## 22. Nguyên tắc sử dụng FederationSchemaFactory

Khai báo FederationSchemaFactory thành Spring bean và gắn factory::createGraphQLSchema vào GraphQlSource.Builder qua GraphQlSourceBuilderCustomizer. Để factory phát hiện @EntityMapping controller methods và thiết lập entity resolver cho schema federation.

Khai báo @key đúng với entity identity mà subgraph chia sẻ. Dùng @EntityMapping để đọc representation và tải entity; dùng @SchemaMapping, @BatchMapping hoặc DataLoader cho các field còn lại. Khi batch entity resolution, giữ đúng thứ tự representation và tránh truy vấn riêng cho từng entity nếu có thể gom theo batch.

Kiểm tra _service.sdl và _entities bằng GraphQlTester, sau đó kiểm tra composition với gateway/router thực tế. Bảo vệ entity theo principal/tenant ở từng subgraph, không xem representation là credential. FederationSchemaFactory giải quyết phần schema federation và kết nối entity mapping của Spring; ownership, authorization, query efficiency và supergraph composition vẫn là trách nhiệm thiết kế của hệ thống.

## Tài liệu tham khảo

- [Spring for GraphQL — Federation](https://docs.spring.io/spring-graphql/reference/federation.html)
- [FederationSchemaFactory API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/federation/FederationSchemaFactory.html)
- [EntityMapping API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/federation/EntityMapping.html)
- [Apollo Federation — Subgraph Specification](https://www.apollographql.com/docs/federation/subgraph-spec)
- [Apollo Federation — Entities](https://www.apollographql.com/docs/federation/entities)
