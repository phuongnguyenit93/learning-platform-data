# RuntimeWiringConfigurer

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vai trò của RuntimeWiringConfigurer trong quá trình xây dựng GraphQL runtime.
- Phân biệt SDL, RuntimeWiring, DataFetcher và GraphQL engine.
- Đăng ký DataFetcher, custom scalar và TypeResolver bằng RuntimeWiringConfigurer.
- Tích hợp RuntimeWiringConfigurer với cơ chế auto-configuration của Spring Boot.
- Phối hợp runtime wiring với annotated controller mà không tạo mapping trùng lặp.
- Biết khi nào nên dùng RuntimeWiringConfigurer và khi nào nên dùng các extension point khác của Spring for GraphQL.

## 1. RuntimeWiringConfigurer là gì?

GraphQL SDL mô tả cấu trúc API: type nào tồn tại, field nhận argument gì và kết quả có kiểu nào. SDL chưa tự cung cấp cách lấy dữ liệu cho từng field. Server cần cấu hình runtime để kết nối khai báo trong schema với hành vi thực thi.

Trong Spring for GraphQL, `RuntimeWiringConfigurer` là extension point cho phép ứng dụng tùy chỉnh `RuntimeWiring.Builder` của GraphQL Java.

Interface có phương thức:

~~~java
public interface RuntimeWiringConfigurer {
    void configure(RuntimeWiring.Builder builder);
}
~~~

Một bean triển khai interface này có thể đăng ký các thành phần như:

- DataFetcher cho field trong schema.
- Custom scalar và quy tắc chuyển đổi dữ liệu.
- TypeResolver cho interface hoặc union.
- SchemaDirectiveWiring cho custom directive.
- WiringFactory để cung cấp wiring theo định nghĩa schema.

Có thể hình dung quá trình như sau:

~~~mermaid
flowchart TD
    A[Schema SDL] --> C[GraphQlSource]
    B[RuntimeWiringConfigurer beans] --> D[RuntimeWiring.Builder]
    D --> C
    C --> E[GraphQLSchema]
    E --> F[GraphQL engine]
    F --> G[ExecutionGraphQlService]
    G --> H[HTTP / WebSocket / RSocket]
~~~

`RuntimeWiringConfigurer` được gọi khi Spring xây dựng GraphQL schema/runtime. Nó không phải controller nhận từng request. Các DataFetcher được đăng ký trong giai đoạn cấu hình sẽ được GraphQL engine sử dụng khi thực thi operation.

## 2. Phân biệt SDL, RuntimeWiring và DataFetcher

Ba thành phần này có trách nhiệm khác nhau:

| Thành phần | Trách nhiệm | Ví dụ |
|---|---|---|
| SDL | Khai báo hợp đồng và cấu trúc dữ liệu | `type Query { book(id: ID!): Book }` |
| RuntimeWiring | Kết nối schema với hành vi thực thi | Đăng ký DataFetcher cho `Query.book` |
| DataFetcher | Lấy giá trị cho một field khi query chạy | Gọi repository để tìm Book |

Ví dụ SDL:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
}
~~~

Schema cho biết field `book` nhận argument `id` và trả về `Book`. DataFetcher quyết định cách tìm đối tượng Book theo ID đó.

Nếu chỉ khai báo SDL mà không có DataFetcher hoặc cơ chế property mapping phù hợp, GraphQL vẫn có thể xây dựng schema, nhưng field có thể không trả về dữ liệu như mong đợi.

GraphQL Java có thể dùng `PropertyDataFetcher` mặc định để đọc property từ source object đối với các field object thông thường. Vì vậy, không phải field nào cũng cần đăng ký DataFetcher tường minh.

## 3. Tạo bean RuntimeWiringConfigurer trong Spring Boot

Với Spring Boot GraphQL starter, các bean loại `RuntimeWiringConfigurer` được tự động phát hiện và áp dụng khi xây dựng `GraphQlSource`.

Ví dụ đăng ký DataFetcher cho `Query.book`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
public class BookRuntimeConfiguration {

    @Bean
    RuntimeWiringConfigurer bookDataFetcher(BookRepository repository) {
        return wiringBuilder -> wiringBuilder
                .type("Query", typeBuilder -> typeBuilder
                        .dataFetcher("book", environment -> {
                            String id = environment.getArgument("id");
                            return repository.findById(id).orElse(null);
                        })
                );
    }
}
~~~

Giải thích:

- `@Configuration` khai báo lớp cấu hình Spring.
- `@Bean` đăng ký một đối tượng `RuntimeWiringConfigurer` vào application context.
- `type("Query", ...)` chọn GraphQL object type có tên `Query`.
- `dataFetcher("book", ...)` gắn DataFetcher vào field `Query.book`.
- `environment.getArgument("id")` đọc argument client truyền vào.
- Repository trả về đối tượng Book hoặc null nếu không tìm thấy.

Tên type và field phải khớp với SDL. Nếu schema đổi tên field thành `findBook`, wiring cũng phải cập nhật tương ứng.

### Dùng class triển khai interface

Nếu cấu hình phức tạp, có thể tạo class riêng thay vì viết lambda trong phương thức bean:

~~~java
public class BookRuntimeWiringConfigurer
        implements RuntimeWiringConfigurer {

    private final BookRepository repository;

    public BookRuntimeWiringConfigurer(BookRepository repository) {
        this.repository = repository;
    }

    @Override
    public void configure(RuntimeWiring.Builder builder) {
        builder.type("Query", typeBuilder ->
                typeBuilder.dataFetcher("book", environment -> {
                    String id = environment.getArgument("id");
                    return repository.findById(id).orElse(null);
                })
        );
    }
}
~~~

Đăng ký class này thành bean bằng constructor injection. Cách triển khai tường minh hữu ích khi wiring có nhiều field hoặc cần chia cấu hình theo domain.

## 4. Đọc dữ liệu từ DataFetchingEnvironment

Tham số của DataFetcher thường là `DataFetchingEnvironment`. Đây là context mô tả field đang được thực thi.

Các API thường dùng:

| API | Mục đích |
|---|---|
| `getArgument("name")` | Đọc argument của field |
| `getSource()` | Lấy object cha đang được phân giải |
| `getGraphQlContext()` | Đọc context chung của GraphQL request |
| `getLocalContext()` | Đọc local context được truyền từ field cha |
| `getSelectionSet()` | Kiểm tra các field con client yêu cầu |
| `getField()` | Lấy thông tin field hiện tại |

Ví dụ, một field lồng có thể lấy source object từ field cha:

Giả sử schema bổ sung field `author` cho Book:

~~~graphql
type Book {
  id: ID!
  authorId: ID!
  author: Author
}

type Author {
  id: ID!
  name: String!
}
~~~

~~~java
@Bean
RuntimeWiringConfigurer bookAuthorFetcher(AuthorRepository authorRepository) {
    return builder -> builder.type("Book", typeBuilder ->
            typeBuilder.dataFetcher("author", environment -> {
                Book book = environment.getSource();
                return authorRepository.findById(book.getAuthorId())
                        .orElse(null);
            })
    );
}
~~~

Ở đây, `Book.author` được phân giải dựa trên object Book đã được trả về từ field cha. DataFetcher đọc authorId rồi tải Author tương ứng.

Đối với ứng dụng Spring for GraphQL dùng annotated controller, logic tương tự thường được viết bằng `@SchemaMapping`. Hãy chọn một cơ chế cho từng field để cấu hình dễ hiểu và tránh trùng mapping.

Không lưu dữ liệu theo từng request vào field mutable của một bean RuntimeWiringConfigurer hoặc DataFetcher dùng chung. Bean cấu hình thường được dùng lại giữa nhiều request. Dữ liệu theo request cần lấy từ environment, GraphQL context hoặc các cơ chế request-scoped phù hợp.

## 5. Đăng ký custom scalar

Một scalar tùy chỉnh cần có quy tắc parse input và serialize output. Runtime wiring là nơi đăng ký scalar với tên tương ứng trong SDL.

Ví dụ dùng GraphQL Java Extended Scalars:

~~~java
import graphql.scalars.ExtendedScalars;
import org.springframework.context.annotation.Bean;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Bean
RuntimeWiringConfigurer scalarConfigurer() {
    return builder -> builder
            .scalar(ExtendedScalars.Date)
            .scalar(ExtendedScalars.DateTime);
}
~~~

SDL:

~~~graphql
scalar Date
scalar DateTime

type Appointment {
  serviceDate: Date!
  startsAt: DateTime!
}
~~~

Tên scalar trong SDL phải trùng với scalar được đăng ký. Extended Scalars Date thường chuyển đổi sang `LocalDate`, còn DateTime thường chuyển đổi sang `OffsetDateTime`.

Với custom scalar tự viết, tạo `GraphQLScalarType` và đăng ký qua `builder.scalar(...)`. Phần Coercing của scalar cần xử lý cả `serialize`, `parseValue` và `parseLiteral` khi API hỗ trợ cả variables lẫn literal.

## 6. Đăng ký TypeResolver cho interface và union

GraphQL interface và union là abstract type. Khi DataFetcher trả về một Java object, GraphQL cần xác định concrete GraphQL object type tương ứng.

Ví dụ SDL:

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

Runtime wiring có thể đăng ký TypeResolver:

~~~java
@Bean
RuntimeWiringConfigurer searchResultTypeResolver() {
    return builder -> builder.type("SearchResult", typeBuilder ->
            typeBuilder.typeResolver(environment -> {
                Object source = environment.getObject();

                if (source instanceof BookResult) {
                    return environment.getSchema()
                            .getObjectType("Book");
                }

                if (source instanceof AuthorResult) {
                    return environment.getSchema()
                            .getObjectType("Author");
                }

                throw new IllegalStateException(
                        "Unsupported SearchResult type: "
                                + source.getClass().getName());
            })
    );
}
~~~

TypeResolver chỉ xác định concrete type. Nó không tải dữ liệu cho field `title`, `name` hoặc `id`. Các field đó tiếp tục được phân giải bằng property fetcher, DataFetcher hoặc annotated controller mapping.

Spring for GraphQL có cơ chế `ClassNameTypeResolver` mặc định để suy ra GraphQL type từ tên class theo quy ước. Chỉ cần đăng ký TypeResolver riêng khi quy ước mặc định không phù hợp hoặc ứng dụng cần kiểm soát rõ cách xác định type.

## 7. Đăng ký custom directive wiring

GraphQL directive có thể gắn metadata hoặc hành vi vào schema element. GraphQL có một số directive chuẩn như `@skip`, `@include`, `@deprecated`, `@specifiedBy`. Ứng dụng cũng có thể khai báo custom directive.

Ví dụ SDL:

~~~graphql
directive @uppercase on FIELD_DEFINITION

type Book {
  title: String! @uppercase
}
~~~

Khi muốn directive thay đổi cách field hoạt động, cần triển khai `SchemaDirectiveWiring` rồi đăng ký với runtime wiring:

~~~java
@Bean
RuntimeWiringConfigurer directiveConfigurer(
        UppercaseDirectiveWiring uppercaseWiring) {

    return builder -> builder.directiveWiring(uppercaseWiring);
}
~~~

`UppercaseDirectiveWiring` là class do ứng dụng triển khai. Nó có thể can thiệp vào field definition và DataFetcher tương ứng trong quá trình xây dựng schema.

Không phải directive nào cũng cần custom wiring. Một số directive được GraphQL engine xử lý sẵn. Chỉ đăng ký `SchemaDirectiveWiring` cho directive ứng dụng tự định nghĩa hoặc cần hành vi tùy chỉnh.

## 8. Nhiều RuntimeWiringConfigurer trong một ứng dụng

Một ứng dụng có thể có nhiều bean `RuntimeWiringConfigurer`, mỗi bean chịu trách nhiệm cho một phần runtime:

~~~java
@Configuration
public class GraphQlRuntimeConfiguration {

    @Bean
    RuntimeWiringConfigurer dateScalarConfigurer() {
        return builder -> builder.scalar(ExtendedScalars.Date);
    }

    @Bean
    RuntimeWiringConfigurer dateTimeScalarConfigurer() {
        return builder -> builder.scalar(ExtendedScalars.DateTime);
    }
}
~~~

Việc chia nhỏ configurer giúp mỗi cấu hình có trách nhiệm rõ ràng:

- Một configurer đăng ký scalar Date.
- Một configurer đăng ký scalar DateTime.
- Một configurer đăng ký TypeResolver.
- Một configurer đăng ký DataFetcher cho field đặc thù.
- Một configurer đăng ký directive wiring.

Spring Boot thu thập các bean configurer và áp dụng chúng khi xây dựng GraphQL runtime. Khi nhiều configurer cùng tác động đến một type hoặc field, hãy kiểm tra xem chúng có đang ghi đè hoặc xung đột cấu hình hay không. Không nên dựa vào thứ tự ngẫu nhiên để quyết định DataFetcher nào thắng.

Nên giữ mỗi field chỉ có một nơi chịu trách nhiệm mapping chính. Nếu một field đã được xử lý bằng `@QueryMapping` hoặc `@SchemaMapping`, không nên đồng thời đăng ký DataFetcher khác cho chính field đó trừ khi có lý do rõ ràng và đã kiểm tra cách cấu hình được hợp nhất.

## 9. RuntimeWiringConfigurer và annotated controllers

Spring for GraphQL hỗ trợ hai phong cách chính để kết nối field với logic Java:

| Cách làm | Khi phù hợp |
|---|---|
| `RuntimeWiringConfigurer` và DataFetcher | Cần kiểm soát trực tiếp GraphQL Java runtime wiring |
| `@QueryMapping`, `@MutationMapping`, `@SchemaMapping` | Muốn viết resolver bằng annotated controller của Spring |

Annotated controller được Spring tích hợp thông qua `AnnotatedControllerConfigurer`, thành phần này tham gia quá trình runtime wiring. Vì vậy, với Spring Boot starter, các controller được phát hiện và đăng ký tự động.

Ví dụ controller:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id);
    }
}
~~~

Trong trường hợp này, không cần thêm DataFetcher cho `Query.book` trong một RuntimeWiringConfigurer khác.

Dùng RuntimeWiringConfigurer khi cần tích hợp ở tầng GraphQL Java như custom scalar, TypeResolver hoặc directive wiring. Dùng annotated controller cho logic nghiệp vụ của Query, Mutation và field mapping nếu đó là phong cách chính của ứng dụng.

Nếu tự tạo `GraphQlSource` thủ công thay vì dùng auto-configuration, cần bảo đảm builder nhận đủ các configurer cần thiết, bao gồm configurer đăng ký annotated controllers nếu muốn tiếp tục sử dụng controller mapping.

## 10. RuntimeWiringConfigurer khác các extension point nào?

Không phải mọi tùy chỉnh GraphQL đều thuộc RuntimeWiring.

| Extension point | Phạm vi |
|---|---|
| `RuntimeWiringConfigurer` | DataFetcher, scalar, TypeResolver, directive wiring và các thành phần RuntimeWiring |
| `GraphQlSourceBuilderCustomizer` | Tùy chỉnh quá trình xây dựng GraphQlSource trong Spring Boot |
| `Instrumentation` | Quan sát hoặc can thiệp vào quá trình thực thi GraphQL |
| `DataFetcherExceptionResolver` | Chuyển lỗi phát sinh từ DataFetcher thành GraphQL errors |
| `WebGraphQlInterceptor` | Xử lý request/response ở tầng Web GraphQL transport |
| `@SchemaMapping` | Mapping một field cụ thể bằng annotated controller |

Ví dụ, nếu cần đo thời gian thực thi operation hoặc gắn instrumentation vào GraphQL engine, hãy dùng cơ chế instrumentation. Nếu cần chuyển exception thành thông báo lỗi GraphQL có cấu trúc, hãy dùng `DataFetcherExceptionResolver`.

Không nên dùng RuntimeWiringConfigurer để giải quyết một vấn đề thuộc transport hoặc vòng đời request.

## 11. Kiểm thử RuntimeWiringConfigurer

Một configurer cần được kiểm thử ở hai mức:

1. Cấu hình runtime có đăng ký đúng thành phần vào schema hay không.
2. GraphQL operation thực tế có trả dữ liệu và xử lý lỗi đúng hay không.

Ví dụ kiểm thử qua `GraphQlTester`:

~~~java
@Test
void shouldResolveBookUsingRuntimeDataFetcher() {
    graphQlTester.document("""
            query {
                book(id: "b-01") {
                    id
                    title
                }
            }
            """)
            .execute()
            .path("book.id")
            .entity(String.class)
            .isEqualTo("b-01");
}
~~~

Các tình huống nên kiểm tra:

- Field có DataFetcher trả đúng dữ liệu.
- Argument được đọc đúng kiểu và đúng tên.
- ID không tồn tại được xử lý theo nullability của SDL.
- Custom scalar parse variables và serialize output đúng định dạng.
- TypeResolver chọn đúng concrete type cho interface hoặc union.
- Custom directive có tác dụng như hợp đồng đã mô tả.
- Không có field bị đăng ký mapping trùng hoặc bị ghi đè ngoài ý muốn.

Nếu chỉ test lambda riêng mà không khởi tạo GraphQL runtime, có thể bỏ sót lỗi tên field, schema hoặc wiring. Integration test dùng schema SDL thật giúp phát hiện các vấn đề này sớm hơn.

## 12. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Field luôn trả null | Sai tên type hoặc field trong wiring | Đối chiếu với SDL |
| DataFetcher không được gọi | Configurer không được đăng ký thành bean hoặc source không nhận configurer | Kiểm tra Spring application context và GraphQlSource |
| Custom scalar không hoạt động | SDL và tên scalar đăng ký không khớp | Kiểm tra scalar name và coercing |
| Interface/union không resolve được | Thiếu hoặc sai TypeResolver | Kiểm tra Java object và GraphQL object type |
| Mapping controller không hoạt động khi tự tạo source | Thiếu AnnotatedControllerConfigurer | Đưa controller configurer vào runtime wiring |
| Kết quả bị ghi đè | Nhiều configurer đăng ký cùng field | Chỉ định một nơi sở hữu mapping |
| Request khác nhau nhưng dùng chung dữ liệu sai | Lưu state theo request trong bean dùng chung | Lấy dữ liệu từ DataFetchingEnvironment hoặc GraphQL context |

## 13. Nguyên tắc tổ chức RuntimeWiringConfigurer

Khi triển khai thực tế:

- Chia configurer theo trách nhiệm hoặc domain.
- Dùng constructor injection để cung cấp repository và service cho DataFetcher.
- Giữ configurer và DataFetcher không lưu state thay đổi theo request.
- Dùng tên GraphQL type và field chính xác theo SDL.
- Đăng ký custom scalar, TypeResolver và directive wiring tại một vị trí dễ tìm.
- Tránh đăng ký hai cơ chế mapping cho cùng field.
- Tận dụng annotated controller cho resolver nghiệp vụ thông thường.
- Kiểm thử GraphQL operation trên schema thực tế sau khi cấu hình runtime.

RuntimeWiringConfigurer nên được xem là tầng tích hợp giữa schema và GraphQL Java runtime. Nó không nên trở thành nơi chứa toàn bộ nghiệp vụ của ứng dụng. DataFetcher nên điều phối đến service phù hợp và để service xử lý quy tắc domain.

## Kết luận

`RuntimeWiringConfigurer` là extension point của Spring for GraphQL để tùy chỉnh `RuntimeWiring.Builder`. Thông qua nó, ứng dụng có thể đăng ký DataFetcher, custom scalar, TypeResolver và custom directive wiring để GraphQL Java thực thi schema SDL.

Với Spring Boot, các bean RuntimeWiringConfigurer được phát hiện tự động khi tạo GraphQlSource. Annotated controller cũng tham gia runtime wiring thông qua AnnotatedControllerConfigurer. Hiểu ranh giới giữa các cơ chế này giúp chọn đúng công cụ, tránh mapping trùng lặp và giữ cấu hình GraphQL dễ kiểm thử, bảo trì.

## Tài liệu tham khảo

- [Spring for GraphQL — Request Execution and Runtime Wiring](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring Boot — Spring for GraphQL](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [GraphQL Java — RuntimeWiring API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/schema/idl/RuntimeWiring.html)
