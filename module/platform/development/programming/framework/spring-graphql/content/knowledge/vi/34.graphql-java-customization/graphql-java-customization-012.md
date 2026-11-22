# Khi dùng GraphQL Java trực tiếp

Spring for GraphQL được xây dựng trên GraphQL Java. Trong ứng dụng Spring thông thường, bạn khai báo schema SDL, dùng controller hoặc RuntimeWiringConfigurer để đăng ký DataFetcher, rồi để Spring quản lý GraphQlSource, GraphQL execution và transport HTTP/WebSocket.

Tuy nhiên, có những tình huống cần làm việc trực tiếp với GraphQL Java: xây một thư viện GraphQL độc lập, nhúng GraphQL vào một tiến trình không dùng Spring, tạo schema động, viết công cụ kiểm tra schema, kiểm thử execution engine, hoặc tùy biến sâu execution strategy và instrumentation.

**GraphQL Java là execution engine**. Thư viện này nhận GraphQL schema và operation, gọi DataFetcher, kiểm tra dữ liệu đầu vào, thực thi field selection và tạo ExecutionResult. Nó không tự cung cấp HTTP server, authentication, connection đến database hay cơ chế deploy router.

Bài này hướng dẫn cách tạo executable schema bằng SDL và RuntimeWiring, khởi tạo GraphQL instance, thực thi operation, đọc ExecutionResult, truy cập DataFetchingEnvironment, xử lý lỗi, tùy biến type resolver/scalar/directive, sử dụng DataLoader, execution strategy, instrumentation và subscription. Cuối bài phân biệt khi nào nên dùng GraphQL Java trực tiếp và khi nào nên giữ các abstraction của Spring for GraphQL.

## 1. GraphQL Java nằm ở đâu trong kiến trúc?

Một ứng dụng GraphQL server thường có các lớp:

~~~mermaid
flowchart TD
    A[Client] --> B[HTTP / WebSocket transport]
    B --> C[Authentication and request context]
    C --> D[GraphQL request adapter]
    D --> E[GraphQL Java execution engine]
    E --> F[Schema and RuntimeWiring]
    F --> G[DataFetcher]
    G --> H[Application services]
    H --> I[Database / remote services]
~~~

GraphQL Java tập trung ở phần execution engine, schema và DataFetcher. Transport nhận bytes hoặc JSON từ client, chuyển thành GraphQL request và gửi kết quả trở lại qua HTTP, WebSocket hoặc một giao thức khác. Các phần này cần framework hoặc adapter riêng.

Trong Spring for GraphQL:

- GraphQlSource cung cấp GraphQL instance và builder để tạo schema/runtime.
- ExecutionGraphQlService gọi GraphQL Java để thực thi request theo cách không phụ thuộc transport.
- WebGraphQlHandler bổ sung xử lý request/response ở tầng WebGraphQL.
- HTTP, WebSocket và các transport khác chuyển request tới ExecutionGraphQlService.
- RuntimeWiringConfigurer và AnnotatedControllerConfigurer đăng ký DataFetcher, scalar, directive và TypeResolver.

Khi dùng GraphQL Java trực tiếp, bạn tự chịu trách nhiệm tạo và quản lý các thành phần cần thiết. Điều đó hữu ích cho thư viện hoặc công cụ độc lập, nhưng một server production vẫn phải có transport, authentication, giới hạn request, observability và quản lý lifecycle.

## 2. Thêm GraphQL Java vào ứng dụng Java

GraphQL Java được phát hành trên Maven Central với artifact com.graphql-java:graphql-java. Dùng version tương thích với Java runtime và các thư viện liên quan của dự án:

~~~gradle
repositories {
    mavenCentral()
}

dependencies {
    implementation("com.graphql-java:graphql-java:<graphql-java-version>")
}
~~~

Không nên chọn version mới nhất một cách độc lập nếu dự án đang dùng Spring for GraphQL. Spring for GraphQL và Spring Boot quản lý một dải phiên bản GraphQL Java tương thích; hãy dùng dependency management/BOM của dự án hoặc kiểm tra compatibility matrix trước khi override.

Các package thường gặp:

| Package | Vai trò |
|---|---|
| graphql | GraphQL, ExecutionInput, ExecutionResult |
| graphql.schema | GraphQLSchema, DataFetcher, DataFetchingEnvironment, GraphQLObjectType |
| graphql.schema.idl | SchemaParser, TypeDefinitionRegistry, RuntimeWiring, SchemaGenerator |
| graphql.execution | ExecutionStrategy và xử lý lỗi DataFetcher |
| graphql.execution.instrumentation | Instrumentation và lifecycle hooks |
| graphql.execution.preparsed | Cache/parse-and-validate hooks |

## 3. Tạo executable schema từ SDL

GraphQL Java hỗ trợ hai cách xây schema:

1. Khai báo type bằng Java code.
2. Khai báo type bằng Schema Definition Language (SDL), sau đó nối schema với logic runtime qua RuntimeWiring.

Với phần lớn API có schema ổn định, nên ưu tiên SDL vì schema dễ đọc, review, kiểm tra và chia sẻ giữa client/server. Tạo schema hoàn toàn bằng Java phù hợp hơn khi xây công cụ sinh schema động hoặc thư viện cần tạo type theo metadata.

Ví dụ SDL:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  published: Boolean!
}
~~~

Schema này định nghĩa hình dạng dữ liệu, nhưng chưa cho biết field book lấy dữ liệu từ đâu. RuntimeWiring sẽ nối field Query.book với DataFetcher.

~~~java
String sdl = """
        type Query {
          book(id: ID!): Book
        }

        type Book {
          id: ID!
          title: String!
          published: Boolean!
        }
        """;

TypeDefinitionRegistry registry =
        new SchemaParser().parse(sdl);

RuntimeWiring wiring = RuntimeWiring.newRuntimeWiring()
        .type("Query", type -> type.dataFetcher("book", environment -> {
            String id = environment.getArgument("id");
            return bookRepository.findById(id).orElse(null);
        }))
        .build();

GraphQLSchema schema =
        new SchemaGenerator().makeExecutableSchema(registry, wiring);
~~~

Các thành phần chính:

- SchemaParser đọc SDL và tạo TypeDefinitionRegistry.
- RuntimeWiring đăng ký DataFetcher, custom scalar, directive và TypeResolver.
- SchemaGenerator kết hợp registry với wiring để tạo GraphQLSchema thực thi được.

Nếu một field không có DataFetcher riêng, GraphQL Java thường dùng PropertyDataFetcher để đọc property tương ứng từ JavaBean hoặc Map. Vì vậy, chỉ cần đăng ký DataFetcher cho những field cần truy cập service, database hoặc áp dụng logic đặc biệt.

## 4. Tạo schema hoàn toàn bằng Java

Khi schema được tạo từ metadata hoặc cấu trúc type chỉ biết ở runtime, có thể tạo GraphQLObjectType và GraphQLFieldDefinition bằng builder:

~~~java
GraphQLObjectType queryType = GraphQLObjectType.newObject()
        .name("Query")
        .field(field -> field
                .name("hello")
                .type(Scalars.GraphQLString)
                .dataFetcher(environment -> "Hello from GraphQL Java"))
        .build();

GraphQLSchema schema = GraphQLSchema.newSchema()
        .query(queryType)
        .build();

GraphQL graphQL = GraphQL.newGraphQL(schema).build();
~~~

GraphQL Java cung cấp các builder cho object, interface, union, enum, input object, scalar và field. Cách này cho phép tạo schema động, nhưng code sẽ dài hơn SDL và khó review khi schema lớn.

Không nên trộn hai cách xây schema một cách tùy tiện. Nếu phần lớn type ổn định, hãy giữ SDL làm nguồn chính và chỉ tùy biến RuntimeWiring. Chỉ dùng schema programmatic cho phần thực sự cần sinh động.

## 5. Tạo GraphQL instance và thực thi operation

Sau khi có GraphQLSchema, tạo GraphQL instance:

~~~java
GraphQL graphQL = GraphQL.newGraphQL(schema).build();
~~~

GraphQL instance có thể được tái sử dụng cho nhiều request nếu schema và các thành phần cấu hình là bất biến hoặc an toàn khi dùng đồng thời. Không tạo lại schema và GraphQL instance cho mỗi request.

### 5.1. ExecutionInput

ExecutionInput mô tả một lần thực thi. Ngoài query document, nó có thể chứa operation name, variables, context, root object, locale và DataLoaderRegistry.

~~~java
ExecutionInput input = ExecutionInput.newExecutionInput()
        .query("""
                query FindBook($id: ID!) {
                  book(id: $id) {
                    id
                    title
                  }
                }
                """)
        .operationName("FindBook")
        .variables(Map.of("id", "book-01"))
        .build();
~~~

Không nối giá trị user input trực tiếp vào GraphQL document. Hãy truyền chúng qua variables để GraphQL Java thực hiện coercion và validation theo schema.

### 5.2. execute và executeAsync

Có hai cách thực thi phổ biến:

~~~java
ExecutionResult result = graphQL.execute(input);
~~~

~~~java
CompletableFuture<ExecutionResult> future = graphQL.executeAsync(input);
~~~

execute trả ExecutionResult sau khi execution hoàn tất. executeAsync trả CompletableFuture để caller kết hợp với luồng bất đồng bộ của ứng dụng. Không gọi join hoặc get trên event-loop thread của WebFlux để chờ future.

Một DataFetcher cũng có thể trả CompletionStage. GraphQL Java kết hợp các kết quả bất đồng bộ vào toàn bộ execution result; cách chọn Executor và cách thực hiện I/O vẫn do DataFetcher hoặc application service quyết định.

### 5.3. ExecutionResult

ExecutionResult chứa data và errors. GraphQL cho phép response có partial data khi một field lỗi nhưng các field khác vẫn thực thi thành công.

~~~java
ExecutionResult result = graphQL.execute(input);

Object data = result.getData();
List<GraphQLError> errors = result.getErrors();
Map<String, Object> response = result.toSpecification();
~~~

toSpecification() tạo cấu trúc map theo GraphQL response specification, bao gồm data, errors và extensions nếu có. Đây là cấu trúc phù hợp để transport adapter chuyển thành JSON.

Không giả định errors rỗng chỉ vì data khác null. Cũng không giả định data luôn khác null: lỗi parse, validation hoặc lỗi ở root field có thể khiến data không có hoặc null.

## 6. DataFetcher và DataFetchingEnvironment

Mỗi field trong GraphQL schema có một DataFetcher. DataFetcher là hàm lấy giá trị cho field; trong một số hệ sinh thái, thành phần này còn được gọi là resolver.

Ví dụ đăng ký DataFetcher trực tiếp:

~~~java
DataFetcher<Book> bookFetcher = environment -> {
    String id = environment.getArgument("id");
    return bookService.findById(id);
};

RuntimeWiring wiring = RuntimeWiring.newRuntimeWiring()
        .type("Query", type -> type.dataFetcher("book", bookFetcher))
        .build();
~~~

Mỗi lần field Query.book được thực thi, GraphQL Java gọi DataFetcher và truyền vào DataFetchingEnvironment.

### 6.1. Các thông tin quan trọng trong DataFetchingEnvironment

| Method | Ý nghĩa |
|---|---|
| getArgument(name) | Lấy argument đã được parse và coercion theo schema |
| getArguments() | Lấy toàn bộ argument của field |
| getSource() | Object cha được trả về từ field trước đó |
| getRoot() | Root object ban đầu của operation |
| getGraphQlContext() | Context dùng chung trong phạm vi một execution |
| getLocalContext() | Context được truyền từ DataFetcher cha qua DataFetcherResult |
| getExecutionStepInfo() | Thông tin field/type/path trong execution tree |
| getSelectionSet() | Các field con mà client đã chọn |
| getExecutionId() | ID của execution hiện tại |
| getDataLoader(name) | Lấy DataLoader đã đăng ký trong request |

DataFetchingEnvironment là nguồn thông tin quan trọng khi cần viết DataFetcher tổng quát. Tuy nhiên, không nên dùng nó như một service locator để lấy mọi dependency. Hãy inject service hoặc repository qua constructor của object chứa DataFetcher.

### 6.2. Source object và PropertyDataFetcher

Kết quả của field cha trở thành source object cho các field con. Ví dụ DataFetcher Query.book trả về Book, khi GraphQL Java resolve Book.title thì source chính là object Book đó.

Nếu không đăng ký DataFetcher riêng, PropertyDataFetcher tìm property theo tên field trên JavaBean hoặc Map:

~~~java
public record Book(String id, String title) {
}
~~~

Với type Book có field id và title, GraphQL Java có thể đọc accessor id() và title() từ record. Với JavaBean, nó tìm getter theo quy ước như getTitle().

Nếu tên property trong Java khác tên field GraphQL, có thể đăng ký PropertyDataFetcher với property name cụ thể hoặc cung cấp DataFetcher riêng. Không nên dựa vào annotation Jackson để đổi tên field GraphQL: GraphQL Java xây response từ field selection và property fetcher, không phải một bước serialize toàn bộ object bằng Jackson.

### 6.3. GraphQLContext và local context

GraphQLContext lưu dữ liệu dùng chung trong một execution, ví dụ tenant ID, principal hoặc thông tin correlation. Có thể tạo context khi build ExecutionInput:

~~~java
ExecutionInput input = ExecutionInput.newExecutionInput()
        .query("{ currentTenant }")
        .graphQLContext(context -> context.put("tenantId", tenantId))
        .build();
~~~

DataFetcher đọc giá trị:

~~~java
DataFetcher<String> tenantFetcher = environment ->
        environment.getGraphQlContext().get("tenantId");
~~~

GraphQLContext có phạm vi một execution. Không dùng một Map mutable toàn cục làm context cho nhiều request vì dữ liệu của người dùng này có thể rò sang request khác.

Local context có phạm vi nhánh của execution tree. DataFetcher cha có thể trả DataFetcherResult chứa localContext; các DataFetcher con nhận giá trị đó qua getLocalContext(). Dùng local context khi dữ liệu chỉ liên quan đến một nhánh, không phải toàn request.

### 6.4. DataFetcherResult: data, errors và local context

DataFetcherResult cho phép DataFetcher trả dữ liệu cùng GraphQL errors hoặc local context:

~~~java
return DataFetcherResult.<Book>newResult()
        .data(book)
        .localContext(Map.of("canEdit", canEdit))
        .build();
~~~

Khi cần trả data kèm một lỗi có thể tiếp tục xử lý, có thể thêm error vào builder:

~~~java
return DataFetcherResult.<Book>newResult()
        .data(book)
        .error(GraphqlErrorBuilder.newError(environment)
                .message("Một số metadata không thể tải")
                .build())
        .build();
~~~

Đây là cách biểu diễn partial result ở cấp field. Chỉ thêm lỗi khi client cần biết một phần dữ liệu bị thiếu hoặc không đầy đủ; không biến mọi tình huống bình thường thành GraphQL error.

## 7. RuntimeWiring và các thành phần mở rộng schema

RuntimeWiring không chỉ đăng ký DataFetcher. Nó còn là nơi đăng ký custom scalar, TypeResolver cho interface/union, directive wiring và các thành phần runtime khác.

~~~java
RuntimeWiring wiring = RuntimeWiring.newRuntimeWiring()
        .type("Query", type -> type
                .dataFetcher("book", bookFetcher))
        .scalar(dateScalar)
        .type("SearchResult", type -> type.typeResolver(searchResultTypeResolver))
        .directive("auth", new AuthorizationDirectiveWiring())
        .build();
~~~

Chỉ đăng ký các thành phần mà schema thực sự sử dụng. Nếu type hoặc directive trong SDL không có runtime wiring tương ứng, schema có thể không được tạo hoặc field không hoạt động như mong đợi.

### 7.1. TypeResolver cho interface và union

GraphQL interface và union có thể trả về nhiều object type. GraphQL Java cần TypeResolver để xác định object type cụ thể của giá trị runtime.

Ví dụ schema:

~~~graphql
interface SearchResult {
  id: ID!
}

type Book implements SearchResult {
  id: ID!
  title: String!
}

type Author implements SearchResult {
  id: ID!
  name: String!
}

type Query {
  search: [SearchResult!]!
}
~~~

Đăng ký resolver:

~~~java
TypeResolver searchResultTypeResolver = environment -> {
    Object value = environment.getObject();
    if (value instanceof Book) {
        return environment.getSchema().getObjectType("Book");
    }
    if (value instanceof Author) {
        return environment.getSchema().getObjectType("Author");
    }
    throw new IllegalArgumentException(
            "Unsupported SearchResult: " + value.getClass().getName());
};

RuntimeWiring wiring = RuntimeWiring.newRuntimeWiring()
        .type("SearchResult", type -> type.typeResolver(searchResultTypeResolver))
        .build();
~~~

TypeResolver phải trả về GraphQLObjectType đã có trong schema. Nếu trả về type không phù hợp hoặc không xác định được runtime class, GraphQL execution sẽ phát sinh lỗi ở field interface/union.

### 7.2. Custom scalar

GraphQL có các scalar chuẩn như String, Int, Float, Boolean và ID. Khi domain dùng kiểu như LocalDate, UUID hoặc Decimal, có thể định nghĩa custom scalar để quy định cách serialize và parse input.

Custom scalar thường cần ba thao tác:

- serialize: chuyển giá trị Java thành giá trị có thể gửi về client.
- parseValue: chuyển input variable thành kiểu Java.
- parseLiteral: chuyển giá trị literal trong GraphQL document thành kiểu Java.

~~~java
GraphQLScalarType dateScalar = GraphQLScalarType.newScalar()
        .name("LocalDate")
        .description("ISO-8601 calendar date")
        .coercing(new LocalDateCoercing())
        .build();
~~~

LocalDateCoercing là implementation của Coercing dành cho LocalDate. Cần xử lý input không hợp lệ bằng CoercingParseValueException hoặc CoercingParseLiteralException và output không hợp lệ bằng CoercingSerializeException theo API của phiên bản GraphQL Java đang dùng.

Đăng ký scalar trong RuntimeWiring bằng scalar(dateScalar). Custom scalar cần có contract rõ ràng về định dạng, timezone và độ chính xác; không nên tự động nhận nhiều định dạng đầu vào mơ hồ.

### 7.3. Schema directive

Schema directive cho phép gắn hành vi dùng chung vào type hoặc field. Ví dụ, directive auth có thể kiểm tra quyền trước khi gọi DataFetcher gốc:

~~~graphql
directive @auth(role: String!) on FIELD_DEFINITION

type Employee {
  id: ID!
  name: String!
  salary: Float @auth(role: "manager")
}
~~~

Implementation có thể bọc DataFetcher gốc:

~~~java
class AuthorizationDirectiveWiring implements SchemaDirectiveWiring {

    @Override
    public GraphQLFieldDefinition onField(
            SchemaDirectiveWiringEnvironment<GraphQLFieldDefinition> environment) {

        String role = (String) environment.getAppliedDirective()
                .getArgument("role")
                .getArgumentValue()
                .getValue();

        DataFetcher<?> original = environment.getFieldDataFetcher();
        DataFetcher<?> secured = dataEnvironment -> {
            AuthorizationContext auth = dataEnvironment.getGraphQlContext()
                    .get("authContext");
            if (!auth.hasRole(role)) {
                return null;
            }
            return original.get(dataEnvironment);
        };

        return environment.setFieldDataFetcher(secured);
    }
}
~~~

Đăng ký bằng RuntimeWiring.directive("auth", wiring). Trước khi thực thi, đưa AuthorizationContext của request vào GraphQLContext. Ví dụ trả null chỉ minh họa một chính sách ẩn field; API production có thể cần trả GraphQL error có mã phù hợp để client phân biệt field bị từ chối.

Directive là cơ chế áp dụng hành vi xuyên suốt schema. Nó không thay thế kiểm tra quyền ở service layer, đặc biệt khi cùng service được gọi từ REST, message consumer hoặc một GraphQL field khác.

### 7.4. Schema directive và operation directive

Hai nhóm directive có vị trí và thời điểm xử lý khác nhau:

| Nhóm | Được khai báo/đặt ở đâu | Cách đọc |
|---|---|---|
| Schema directive | SDL trên schema, type, field hoặc argument | SchemaDirectiveWiring trong lúc tạo executable schema |
| Operation directive | Query document trên operation, field, fragment hoặc variable | QueryDirectives qua DataFetchingEnvironment khi execution |

Một operation directive như @cache trên field của query không tự tạo cache. GraphQL Java chỉ parse và cung cấp directive usage; ứng dụng phải viết logic để đọc directive và thực hiện cache.

Trong DataFetcher, có thể đọc directive đã được áp dụng lên field:

~~~java
List<QueryAppliedDirective> cacheDirectives = environment.getQueryDirectives()
        .getImmediateAppliedDirective("cache");

if (!cacheDirectives.isEmpty()) {
    QueryAppliedDirective cache = cacheDirectives.get(0);
    QueryAppliedDirectiveArgument maxAge = cache.getArgument("maxAge");
    Integer maxAgeMillis = maxAge.getValue();
    // Apply the application's cache policy.
}
~~~

Query directive có thể xuất hiện nhiều lần nếu được khai báo repeatable. Hãy xử lý trường hợp danh sách rỗng và nhiều directive thay vì luôn lấy phần tử đầu tiên.

## 8. ExecutionStrategy và xử lý lỗi

ExecutionStrategy quyết định cách GraphQL Java thực thi các field trong một operation. Các chiến lược mặc định phù hợp với phần lớn ứng dụng:

| Operation | Execution strategy | Hành vi |
|---|---|---|
| Query | AsyncExecutionStrategy (mặc định) | Cho phép các field cùng cấp thực thi bất đồng bộ |
| Mutation | AsyncSerialExecutionStrategy (mặc định) | Thực thi các root mutation field theo thứ tự |
| Subscription | SubscriptionExecutionStrategy | Cần dùng để hỗ trợ Reactive Streams Publisher |

Có thể cấu hình strategy khi tạo GraphQL instance:

~~~java
GraphQL graphQL = GraphQL.newGraphQL(schema)
        .queryExecutionStrategy(new AsyncExecutionStrategy())
        .mutationExecutionStrategy(new AsyncSerialExecutionStrategy())
        .subscriptionExecutionStrategy(new SubscriptionExecutionStrategy())
        .build();
~~~

Đây là cấu hình tường minh các chiến lược phổ biến. Chỉ thay strategy khi có yêu cầu cụ thể và hiểu ảnh hưởng tới concurrency, thứ tự mutation, DataLoader và exception handling.

### 8.1. DataFetcher bất đồng bộ

DataFetcher có thể trả về CompletionStage để engine kết hợp kết quả:

~~~java
DataFetcher<CompletableFuture<Book>> bookFetcher = environment -> {
    String id = environment.getArgument("id");
    return CompletableFuture.supplyAsync(
            () -> bookService.findById(id),
            bookExecutor);
};
~~~

Truyền executor rõ ràng cho công việc blocking. Nếu bỏ executor, CompletableFuture.supplyAsync sử dụng ForkJoinPool.commonPool mặc định; không nên dùng common pool làm nơi chạy JDBC hoặc HTTP blocking trong server có tải lớn.

AsyncExecutionStrategy không tự chuyển mọi DataFetcher đồng bộ sang thread pool. DataFetcher trả object trực tiếp vẫn chạy phần code đồng bộ trên thread đang gọi nó.

### 8.2. DataFetcherExceptionHandler

Khi DataFetcher ném exception, GraphQL Java mặc định tạo GraphQL error gắn với field path và source location. Các field khác vẫn có thể trả data, tùy nullability và vị trí lỗi trong response tree.

Có thể tùy biến cách ánh xạ exception:

~~~java
DataFetcherExceptionHandler exceptionHandler = parameters -> {
    GraphQLError error = GraphqlErrorBuilder.newError()
            .message("Không thể tải dữ liệu cho field")
            .path(parameters.getPath())
            .location(parameters.getSourceLocation())
            .errorType(ErrorType.DataFetchingException)
            .build();

    return CompletableFuture.completedFuture(
            DataFetcherExceptionHandlerResult.newResult()
                    .error(error)
                    .build());
};
~~~

Gắn handler vào execution strategy:

~~~java
GraphQL graphQL = GraphQL.newGraphQL(schema)
        .queryExecutionStrategy(new AsyncExecutionStrategy(exceptionHandler))
        .mutationExecutionStrategy(new AsyncSerialExecutionStrategy(exceptionHandler))
        .build();
~~~

Trong ứng dụng thực tế, nên phân loại lỗi nghiệp vụ, lỗi validation và lỗi hệ thống thành GraphQL error type/extension phù hợp. Không gửi stack trace, SQL, access token hoặc thông tin nội bộ trong message trả về client; log chi tiết ở server với execution ID để điều tra.

## 9. DataLoader khi dùng GraphQL Java trực tiếp

Nếu mỗi field con tự gọi database, một operation có thể phát sinh N+1. GraphQL Java hỗ trợ DataLoader để gom nhiều key trong cùng execution thành một batch.

Ví dụ nhiều Book cần Author theo authorId:

~~~java
MappedBatchLoader<String, Author> authorBatchLoader = authorIds ->
        CompletableFuture.supplyAsync(
                () -> authorService.findAllByIds(authorIds),
                authorExecutor);

DataLoader<String, Author> authorLoader =
        DataLoaderFactory.newMappedDataLoader(authorBatchLoader);
~~~

Đăng ký loader vào DataLoaderRegistry của request:

~~~java
DataLoaderRegistry registry = new DataLoaderRegistry();
registry.register("authorById", authorLoader);

ExecutionInput input = ExecutionInput.newExecutionInput()
        .query(query)
        .dataLoaderRegistry(registry)
        .build();
~~~

DataFetcher lấy loader từ DataFetchingEnvironment:

~~~java
DataFetcher<CompletableFuture<Author>> authorFetcher = environment -> {
    Book book = environment.getSource();
    DataLoader<String, Author> loader =
            environment.getDataLoader("authorById");
    return loader.load(book.authorId());
};
~~~

### 9.1. Vòng đời và điều kiện batching

DataLoader có cache và trạng thái dispatch, vì vậy phải tạo DataLoaderRegistry cùng các loader cho từng execution/request. Không dùng chung một registry mutable giữa các request của nhiều người dùng.

Batching của DataLoader dựa trên AsyncExecutionStrategy để biết thời điểm dispatch tối ưu. Nếu dùng execution strategy khác không hỗ trợ cơ chế dispatch này, DataLoader có thể vẫn cache nhưng không gom được các key thành batch như mong đợi.

GraphQL Java tự tích hợp DataLoader dispatch instrumentation trong cấu hình mặc định. Nếu bạn thay instrumentation chain hoặc tự xây GraphQL instance, hãy kiểm tra DataLoaderDispatcherInstrumentation vẫn được cài đặt; có thể đăng ký tường minh khi cần cấu hình statistics.

Kết quả của mapped batch loader phải chứa kết quả cho các key tương ứng. Với batch loader trả về List thay vì Map, thứ tự phần tử phải khớp thứ tự key đầu vào. Kiểm thử trường hợp key không tồn tại, duplicate key và lỗi batch load.

### 9.2. Không enqueue DataLoader từ một tác vụ async khác

Không bọc lời gọi DataLoader.load() trong CompletableFuture.supplyAsync ngay tại DataFetcher:

~~~java
// Không nên: key có thể được enqueue sau thời điểm engine dispatch.
return CompletableFuture.supplyAsync(() -> loader.load(book.authorId()));
~~~

GraphQL Java theo dõi các lời gọi load được enqueue trong quá trình duyệt field tree để chọn thời điểm dispatch. Nếu lời gọi load chỉ xuất hiện sau khi một tác vụ chạy ở thread khác hoàn tất, engine có thể không nhận ra key đúng thời điểm và execution có thể bị treo.

Hãy gọi loader.load() trực tiếp trong DataFetcher như ví dụ trước. Đặt phần I/O bất đồng bộ bên trong BatchLoader/MappedBatchLoader; batch loader được phép trả CompletionStage và chạy công việc trên executor phù hợp.

GraphQL Java 25 có hỗ trợ chained DataLoader nhưng cần bật tường minh bằng GraphQLUnusualConfiguration.DataloaderConfig.enableDataLoaderChaining(true). Chỉ bật khi có nhu cầu và đã kiểm tra thứ tự dispatch của các loader phụ thuộc nhau.

## 10. Instrumentation và profiling

Instrumentation cho phép quan sát hoặc thay đổi các bước trong GraphQL execution. Các ứng dụng thường dùng nó cho timing, tracing, metrics, logging, field interception hoặc gắn metadata vào ExecutionResult.

Một instrumentation có thể quan sát lúc execution bắt đầu và lúc kết thúc:

~~~java
class TimingInstrumentation extends SimplePerformantInstrumentation {

    @Override
    public InstrumentationContext<ExecutionResult> beginExecution(
            InstrumentationExecutionParameters parameters,
            InstrumentationState state) {

        long startNanos = System.nanoTime();
        return new SimpleInstrumentationContext<>() {
            @Override
            public void onCompleted(ExecutionResult result, Throwable throwable) {
                long elapsedNanos = System.nanoTime() - startNanos;
                metrics.recordGraphQlExecution(elapsedNanos);
            }
        };
    }
}
~~~

Đăng ký instrumentation khi tạo GraphQL instance:

~~~java
GraphQL graphQL = GraphQL.newGraphQL(schema)
        .instrumentation(new TimingInstrumentation())
        .build();
~~~

InstrumentationState có thể giữ dữ liệu riêng cho một execution. Không lưu trạng thái request vào field mutable của instrumentation dùng chung nếu không có đồng bộ phù hợp; một GraphQL instance có thể xử lý nhiều request đồng thời.

Có thể kết hợp nhiều instrumentation bằng ChainedInstrumentation. Khi thay instrumentation mặc định, cần kiểm tra các chức năng cần thiết khác như DataLoader dispatch vẫn hoạt động.

### 10.1. Profiling execution

GraphQL Java v25 có profiler cho execution. Có thể bật profiling trên ExecutionInput:

~~~java
ExecutionInput input = ExecutionInput.newExecutionInput()
        .query(query)
        .profileExecution(true)
        .build();
~~~

Sau khi thực thi, ProfilerResult được lưu trong GraphQLContext dưới key ProfilerResult.PROFILER_CONTEXT_KEY:

~~~java
ExecutionResult result = graphQL.execute(input);
ProfilerResult profilerResult = input.getGraphQLContext()
        .get(ProfilerResult.PROFILER_CONTEXT_KEY);

if (profilerResult != null) {
    Map<String, Object> summary = profilerResult.shortSummaryMap();
    logger.info("GraphQL profile: {}", summary);
}
~~~

Profiler giúp xem DataFetcher invocation, DataLoader dispatch và timing của execution. Chỉ bật khi cần phân tích hoặc ở môi trường đã đánh giá chi phí; không log raw query, variables hay dữ liệu nhạy cảm theo mặc định.

## 11. Subscription khi dùng GraphQL Java trực tiếp

Subscription tạo một luồng event. DataFetcher của field subscription trả về Reactive Streams Publisher; GraphQL Java áp dụng selection set lên từng event và phát ra một ExecutionResult cho mỗi lần cập nhật.

Ví dụ schema:

~~~graphql
type StockPrice {
  symbol: String!
  price: Float!
}

type Subscription {
  stockPrice(symbol: String!): StockPrice!
}
~~~

DataFetcher tạo publisher:

~~~java
DataFetcher<Publisher<StockPrice>> stockPriceFetcher = environment -> {
    String symbol = environment.getArgument("symbol");
    return stockPriceService.streamFor(symbol);
};
~~~

Tạo GraphQL instance có SubscriptionExecutionStrategy:

~~~java
GraphQL graphQL = GraphQL.newGraphQL(schema)
        .subscriptionExecutionStrategy(new SubscriptionExecutionStrategy())
        .build();

ExecutionResult initialResult = graphQL.execute(subscriptionInput);
Publisher<ExecutionResult> events =
        (Publisher<ExecutionResult>) initialResult.getData();
~~~

Publisher<ExecutionResult> là stream kết quả. Ứng dụng cần subscribe và quản lý backpressure, cancellation, lỗi nguồn dữ liệu và cleanup khi client ngắt kết nối.

GraphQL Java chỉ tạo stream execution result. Nó không tự gửi stream qua WebSocket hoặc Server-Sent Events. Cần một transport adapter quản lý handshake, xác thực, session, serialization và gửi từng event về client. Spring for GraphQL cung cấp các abstraction transport để xử lý những việc này.

## 12. Những trách nhiệm cần bổ sung cho production server

GraphQL Java tập trung vào schema execution. Khi tự dùng nó để xây server, ứng dụng cần bổ sung các lớp bảo vệ và vận hành:

| Trách nhiệm | Việc cần làm |
|---|---|
| Transport | Nhận HTTP/WebSocket/SSE, parse request envelope và serialize response |
| Authentication | Xác thực credential trước execution |
| Authorization | Kiểm tra quyền trong service hoặc DataFetcher theo từng resource/field |
| Input validation | Dùng schema validation và kiểm tra business constraints |
| Query limits | Giới hạn request size, depth, complexity, alias và số lượng field |
| Timeouts | Giới hạn thời gian cho database, remote API và execution |
| Rate limiting | Giới hạn request theo client, principal hoặc tenant |
| Observability | Ghi execution ID, latency, errors, DataFetcher timing và DataLoader statistics |
| Lifecycle | Quản lý executor, subscription, cancellation và shutdown |

### 12.1. Parse, validation và cache operation

GraphQL Java parse document và validate operation với schema trước khi chạy DataFetcher. Request sai cú pháp hoặc sai schema sẽ trả lỗi validation và không gọi resolver.

Trong server có nhiều request lặp lại cùng document, có thể dùng PreparsedDocumentProvider để cache PreparsedDocumentEntry và tái sử dụng Document đã parse/validation. Cơ chế này tránh lặp lại công việc parse/validation nhưng không cache ExecutionResult. Cache key phải tính đến nội dung document và các yếu tố ảnh hưởng đến validation. Không cache kết quả thực thi theo document đơn thuần vì kết quả còn phụ thuộc variables, người dùng, tenant và dữ liệu hiện tại.

Nếu dùng persisted query, transport adapter cần xác thực hash/document và áp dụng chính sách chỉ cho phép operation đã đăng ký nếu kiến trúc yêu cầu.

### 12.2. Giới hạn độ sâu và độ phức tạp

Một operation có thể yêu cầu nhiều field lồng nhau hoặc nhân số lượng phần tử qua các list. Giới hạn độ sâu (depth) và độ phức tạp (complexity) giúp giảm nguy cơ một query tiêu thụ quá nhiều CPU, database connection hoặc memory.

Giới hạn cần được chọn dựa trên schema và workload thực tế. Một query nông vẫn có thể tốn kém nếu field trả list lớn; một query sâu có thể hợp lệ nếu mỗi nhánh nhỏ. Nên kết hợp depth/complexity với pagination bắt buộc, timeout, request size limit và rate limit.

### 12.3. Authentication và authorization

GraphQL Java không áp đặt mô hình security. DataFetcher cần gọi service layer có kiểm tra quyền trên resource, tenant và hành động tương ứng. Không dựa vào việc client không chọn một field để xem đó là bảo vệ dữ liệu.

Có thể đưa principal hoặc security context đã xác thực vào GraphQLContext, nhưng service layer vẫn cần kiểm tra quyền vì cùng service có thể được gọi từ nhiều entry point khác nhau.

Không đặt access token hoặc secret vào error message, response extensions, metric tag hay raw query log.

### 12.4. Kiểm tra schema mapping

GraphQL Java không tự xác minh rằng mọi field trong schema đều có DataFetcher phù hợp. Field không có DataFetcher riêng có thể dùng PropertyDataFetcher; nếu không tìm được property tương ứng, field có thể trả null mà không có lỗi build schema.

Vì vậy, cần có test bao phủ các field quan trọng, đặc biệt là field non-null, interface/union và các field có DataFetcher đăng ký qua code. Trong ứng dụng Spring for GraphQL, schema mapping inspection có thể giúp phát hiện field chưa được map, registration trỏ tới field không tồn tại hoặc argument không khớp.

## 13. Dùng GraphQL Java customization bên trong Spring for GraphQL

Nếu ứng dụng đã dùng Spring for GraphQL, phần lớn trường hợp không cần tạo GraphQL instance trực tiếp. Spring đã quản lý GraphQlSource, ExecutionGraphQlService, transport và các resolver tích hợp.

Bạn vẫn có thể dùng API GraphQL Java để tùy biến runtime thông qua các extension point của Spring:

| Nhu cầu | Extension point |
|---|---|
| Đăng ký DataFetcher, scalar, directive, TypeResolver | RuntimeWiringConfigurer |
| Tùy chỉnh GraphQL.Builder | GraphQlSourceBuilderCustomizer |
| Tùy biến schema creation | GraphQlSource.Builder.schemaFactory(...) |
| Thêm execution instrumentation | Bean Instrumentation hoặc GraphQlSourceBuilderCustomizer |
| Tùy chỉnh lỗi DataFetcher | DataFetcherExceptionResolver |

### 13.1. Đăng ký DataFetcher qua RuntimeWiringConfigurer

~~~java
@Bean
RuntimeWiringConfigurer bookWiring(BookService bookService) {
    return builder -> builder
            .type("Query", type -> type.dataFetcher("book", environment -> {
                String id = environment.getArgument("id");
                return bookService.findById(id);
            }));
}
~~~

Spring Boot phát hiện RuntimeWiringConfigurer bean và áp dụng vào GraphQlSource builder. Trong ứng dụng dùng annotated controllers, thường nên để AnnotatedControllerConfigurer đăng ký method @QueryMapping/@SchemaMapping. Dùng DataFetcher trực tiếp cho các trường hợp cần tích hợp GraphQL Java ở mức thấp.

### 13.2. Tùy chỉnh GraphQL.Builder

Có thể dùng GraphQlSourceBuilderCustomizer để thêm instrumentation hoặc cấu hình GraphQL.Builder:

~~~java
@Bean
GraphQlSourceBuilderCustomizer graphQlCustomizer() {
    return builder -> builder.configureGraphQl(graphQlBuilder ->
            graphQlBuilder.instrumentation(new TimingInstrumentation()));
}
~~~

Boot starter vẫn tạo GraphQlSource và nối nó với ExecutionGraphQlService. Customizer chỉ thay đổi phần cấu hình được chỉ định.

Nếu thay execution strategy trong Spring, cần giữ cách Spring tạo DataFetcherExceptionHandler từ các DataFetcherExceptionResolver. Nếu tự đặt handler mặc định của GraphQL Java, bạn có thể bỏ qua exception resolvers mà ứng dụng đang dùng.

### 13.3. Khi nào nên dùng GraphQL Java trực tiếp?

| Tình huống | Lựa chọn phù hợp |
|---|---|
| Ứng dụng Spring Boot cung cấp GraphQL API | Spring for GraphQL và GraphQL Java qua extension point |
| Muốn đăng ký custom scalar hoặc directive | RuntimeWiringConfigurer |
| Muốn custom execution strategy hoặc instrumentation | GraphQlSourceBuilderCustomizer |
| Viết công cụ validate/schema generator độc lập | GraphQL Java trực tiếp |
| Nhúng GraphQL vào CLI, desktop app hoặc service không dùng Spring | GraphQL Java trực tiếp |
| Muốn tự triển khai transport/protocol | GraphQL Java cùng transport adapter riêng |

Chỉ nên bỏ Spring abstraction khi ứng dụng thực sự cần kiểm soát execution lifecycle ở mức thấp hoặc không chạy trong Spring. Nếu chỉ cần một custom DataFetcher, scalar, directive hay instrumentation, hãy giữ Spring làm lớp tích hợp và dùng GraphQL Java API qua đúng extension point.

## 14. Kiểm thử GraphQL Java trực tiếp

Khi dùng GraphQL Java trực tiếp, có thể kiểm thử execution mà không cần HTTP server. Tạo schema và GraphQL instance trong test, gọi execute với operation cụ thể rồi kiểm tra data và errors.

~~~java
@Test
void shouldResolveBookById() {
    ExecutionInput input = ExecutionInput.newExecutionInput()
            .query("""
                    query {
                      book(id: "book-01") {
                        id
                        title
                      }
                    }
                    """)
            .build();

    ExecutionResult result = graphQL.execute(input);

    assertThat(result.getErrors()).isEmpty();

    Map<String, Object> data = result.getData();
    Map<String, Object> book = (Map<String, Object>) data.get("book");
    assertThat(book.get("id")).isEqualTo("book-01");
    assertThat(book.get("title")).isEqualTo("GraphQL Java");
}
~~~

Nên có các nhóm test:

1. SDL parse và schema build thành công.
2. Operation hợp lệ trả đúng data.
3. Operation sai cú pháp hoặc sai schema trả validation errors và không gọi DataFetcher.
4. Variables được coercion đúng theo scalar và nullability.
5. DataFetcher exception tạo GraphQL error đúng path và extensions.
6. Interface/union chọn đúng concrete type.
7. Custom scalar parse/serialize đúng và từ chối input sai.
8. DataLoader gom key, xử lý missing key và giữ đúng mapping.
9. Query/mutation dùng execution strategy theo đúng thứ tự.
10. Subscription phát event, xử lý cancellation và kết thúc stream.

Nếu ứng dụng dùng Spring for GraphQL, hãy bổ sung integration test ở tầng WebGraphQlHandler hoặc HTTP transport để kiểm tra request mapping, security context và serialization. Test GraphQL Java trực tiếp chỉ xác minh execution engine, không kiểm tra transport.

## 15. Những lỗi thường gặp khi dùng GraphQL Java trực tiếp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Schema build báo thiếu Query root | SDL không khai báo type Query hoặc root type tùy chỉnh chưa được cấu hình | Khai báo query root và kiểm tra schema definition |
| Field luôn trả null | Chưa đăng ký DataFetcher hoặc PropertyDataFetcher không tìm được property | Kiểm tra RuntimeWiring, source object và getter/record accessor |
| DataFetcher không được gọi | Operation sai cú pháp, sai field/argument hoặc validation thất bại | Đọc ExecutionResult.getErrors() trước khi debug resolver |
| Interface/union báo không xác định type | Thiếu TypeResolver hoặc resolver trả sai object type | Đăng ký TypeResolver và kiểm tra runtime class |
| Custom scalar từ chối dữ liệu hợp lệ | parseValue/parseLiteral/serialize không thống nhất định dạng | Kiểm thử cả variable, literal và output |
| DataLoader không batching | Không dùng AsyncExecutionStrategy hoặc registry không theo request | Kiểm tra execution strategy, dispatcher instrumentation và registry lifecycle |
| Dữ liệu giữa hai request bị lẫn | Dùng chung DataLoaderRegistry hoặc GraphQLContext mutable | Tạo registry/context mới cho mỗi execution |
| Request chậm dù dùng executeAsync | DataFetcher vẫn blocking hoặc chờ future trên event loop | Trả CompletionStage thực sự bất đồng bộ và dùng executor phù hợp |
| Mutation field chạy sai thứ tự | Dùng execution strategy không tuần tự | Dùng AsyncSerialExecutionStrategy cho mutation root fields |
| Subscription không gửi event qua mạng | Chỉ tạo Publisher mà chưa có transport adapter | Kết nối Publisher với WebSocket/SSE transport |
| Custom error handler làm mất error resolver của Spring | Thay handler ở tầng GraphQL.Builder trong ứng dụng Spring | Tích hợp DataFetcherExceptionResolver vào custom strategy |
| Instrumentation không ghi được số liệu | Không đăng ký hoặc bị thay thế trong instrumentation chain | Kiểm tra GraphQL.Builder và ChainedInstrumentation |
| Client nhận stack trace hoặc SQL | Error handler trả nguyên exception message | Ánh xạ lỗi sang message an toàn, log chi tiết ở server |

## 16. Quy trình làm việc khi cần dùng GraphQL Java trực tiếp

1. Xác định có thật sự cần điều khiển execution engine ở mức GraphQL Java hay Spring extension point đã đủ.
2. Chọn version GraphQL Java tương thích với Java runtime và Spring dependency management nếu có.
3. Khai báo schema bằng SDL; chỉ tạo schema bằng Java khi cần sinh type động.
4. Tạo RuntimeWiring cho DataFetcher, TypeResolver, scalar và directive.
5. Tạo GraphQLSchema và khởi tạo một GraphQL instance có thể tái sử dụng.
6. Tạo ExecutionInput riêng cho mỗi request, đưa variables và context vào đúng chỗ.
7. Tạo DataLoaderRegistry mới cho mỗi request nếu operation dùng DataLoader.
8. Chọn execution strategy và exception handler phù hợp; giữ query bất đồng bộ và mutation tuần tự.
9. Bổ sung instrumentation, profiling và query limits theo nhu cầu vận hành.
10. Nếu có subscription, kết nối Publisher với transport và quản lý cancellation.
11. Kiểm thử schema, execution, errors, batching và concurrency.
12. Nếu ứng dụng chạy trong Spring, ưu tiên RuntimeWiringConfigurer và GraphQlSourceBuilderCustomizer để không tạo thêm execution/transport lifecycle song song.

GraphQL Java cung cấp quyền kiểm soát trực tiếp với schema, DataFetcher và execution strategy. Cần dùng đúng phạm vi: SDL mô tả contract, RuntimeWiring kết nối contract với code, GraphQL thực thi operation và ExecutionResult mô tả data/errors. DataLoader, TypeResolver, custom scalar, directive và Instrumentation mở rộng hành vi engine. Với Spring for GraphQL, các API này vẫn có thể được sử dụng qua GraphQlSource và các configurer; chỉ xây server độc lập khi bạn thực sự muốn tự quản lý transport, security, lifecycle và vận hành.

## Tài liệu tham khảo

- GraphQL Java — Getting Started: https://graphql-java.com/documentation/getting-started/
- GraphQL Java — Schema: https://graphql-java.com/documentation/schema/
- GraphQL Java — Data Fetching: https://graphql-java.com/documentation/data-fetching/
- GraphQL Java — Execution: https://graphql-java.com/documentation/execution/
- GraphQL Java — Batching and DataLoader: https://graphql-java.com/documentation/batching/
- GraphQL Java — SDL Directives: https://graphql-java.com/documentation/directives/
- GraphQL Java — Instrumentation: https://graphql-java.com/documentation/instrumentation/
- GraphQL Java — Subscriptions: https://graphql-java.com/documentation/subscriptions/
- Spring for GraphQL — Request Execution and GraphQlSource: https://docs.spring.io/spring-graphql/reference/request-execution.html
- Spring for GraphQL — Standalone Setup: https://docs.spring.io/spring-graphql/reference/standalone-setup.html
