# Khi dùng wiring thủ công

## 1. Runtime wiring là gì?

Schema SDL mô tả hợp đồng GraphQL: có những type nào, mỗi type có field gì, argument nào được chấp nhận và kiểu dữ liệu nào được trả về. Tuy nhiên, SDL không chứa logic Java để lấy dữ liệu, gọi service, chuyển đổi scalar hoặc xác định object type thực tế của một union. Khi thực thi operation, GraphQL cần biết cách nối các khai báo trong schema với những thành phần xử lý ở server. Quá trình cấu hình đó được gọi là **runtime wiring**.

Trong GraphQL Java, runtime wiring được xây dựng thông qua `RuntimeWiring`. Nó có thể đăng ký:

- `DataFetcher` cho field để cung cấp dữ liệu khi field được thực thi.
- `TypeResolver` cho interface và union để xác định object type cụ thể.
- Custom scalar để parse input và serialize output.
- Directive wiring hoặc các thành phần mở rộng khác của GraphQL Java.

Với Spring for GraphQL, ứng dụng thường không cần tự tạo toàn bộ `RuntimeWiring`. Spring cung cấp `RuntimeWiringConfigurer` để bổ sung cấu hình vào quá trình tạo schema. Đây là điểm mở rộng phù hợp khi cần wiring bằng code thay vì chỉ dựa vào annotation trên controller.

## 2. Khi nào nên dùng wiring thủ công?

Spring for GraphQL hỗ trợ hai cách phổ biến để kết nối field trong schema với Java:

1. **Annotation-based mapping:** dùng `@QueryMapping`, `@MutationMapping`, `@SubscriptionMapping` và `@SchemaMapping` trên các controller.
2. **Programmatic runtime wiring:** đăng ký `DataFetcher`, `TypeResolver`, scalar và cấu hình khác thông qua `RuntimeWiringConfigurer`.

Annotation mapping thường dễ đọc và phù hợp với controller nghiệp vụ. Wiring thủ công hữu ích khi:

- Muốn đăng ký một `DataFetcher` bằng lambda hoặc object có thể tái sử dụng.
- Cần cấu hình type resolver cho interface hoặc union.
- Cần đăng ký custom scalar hoặc runtime component của GraphQL Java.
- Có schema được tạo hoặc tổ chức theo cách đặc biệt và cần kiểm soát wiring tập trung.
- Muốn tích hợp một thành phần GraphQL Java không được biểu diễn trực tiếp bằng annotation controller.

Không nên chuyển mọi field sang wiring thủ công chỉ vì có thể làm được. Hãy chọn cách ánh xạ phù hợp với cấu trúc ứng dụng và giữ một nơi chịu trách nhiệm rõ ràng cho từng field. Tránh đăng ký cùng một field vừa bằng annotation controller vừa bằng `DataFetcher` thủ công vì thứ tự cấu hình và quyền sở hữu field sẽ khó theo dõi.

## 3. `RuntimeWiringConfigurer` trong Spring Boot

`RuntimeWiringConfigurer` là functional interface của Spring for GraphQL. Một bean triển khai interface này nhận `RuntimeWiring.Builder` và bổ sung các thành phần cần thiết.

Ví dụ đăng ký `DataFetcher` cho field `Query.book`:

Schema SDL:

```graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
```

Cấu hình Java:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
public class GraphQlRuntimeConfig {

    @Bean
    RuntimeWiringConfigurer bookRuntimeWiring(BookService bookService) {
        return wiringBuilder -> wiringBuilder.type(
            "Query",
            typeWiring -> typeWiring.dataFetcher(
                "book",
                environment -> {
                    String id = environment.getArgument("id");
                    return bookService.findById(id).orElse(null);
                }
            )
        );
    }
}
```

Spring Boot phát hiện bean `RuntimeWiringConfigurer` và áp dụng nó trong quá trình xây dựng GraphQL runtime wiring. `wiringBuilder.type("Query", ...)` chọn object type `Query`; `dataFetcher("book", ...)` đăng ký hàm xử lý field `book`.

`BookService` là service do ứng dụng cung cấp. Spring quản lý dependency và truyền service vào phương thức tạo bean. Vì vậy, `DataFetcher` có thể gọi trực tiếp tầng nghiệp vụ mà không cần tự tạo service hoặc truy cập database từ cấu hình GraphQL.

Nếu ứng dụng đã dùng auto-configuration của Spring Boot, thông thường chỉ cần khai báo bean `RuntimeWiringConfigurer`. Không cần tự tạo `GraphQlSource` chỉ để thêm một data fetcher.

## 4. Đọc dữ liệu từ `DataFetchingEnvironment`

`DataFetcher` nhận một `DataFetchingEnvironment`. Đối tượng này chứa ngữ cảnh của field đang được thực thi, chẳng hạn argument, source object, GraphQL context, locale và thông tin selection set.

| API | Mục đích |
| --- | --- |
| `getArgument("name")` | Lấy argument của field hiện tại |
| `getSource()` | Lấy object cha đang được phân giải |
| `getGraphQlContext()` | Truy cập context dùng chung trong GraphQL execution |
| `getLocalContext()` | Truy cập local context được truyền từ field cha |
| `getLocale()` | Lấy locale của execution |
| `getSelectionSet()` | Kiểm tra các field con mà client yêu cầu |
| `getDataLoader("name")` | Lấy DataLoader đã đăng ký theo tên |

Ví dụ lấy argument:

```java
DataFetcher<Book> bookFetcher = environment -> {
    String id = environment.getArgument("id");
    return bookService.findById(id).orElse(null);
};
```

Ví dụ dùng source object để phân giải field lồng nhau:

```java
DataFetcher<Author> authorFetcher = environment -> {
    Book book = environment.getSource();
    return authorService.findById(book.authorId()).orElse(null);
};
```

Khi field `author` được thực thi bên trong một `Book`, `getSource()` trả về đối tượng `Book` cha. Data fetcher có thể dùng khóa liên kết để tải `Author` tương ứng.

GraphQL context có thể chứa thông tin đã được ứng dụng đưa vào execution context, ví dụ correlation ID hoặc thông tin tenant:

```java
String tenantId = environment.getGraphQlContext().get("tenantId");
```

Context không tự xuất hiện chỉ vì resolver gọi `getGraphQlContext()`. Ứng dụng phải thiết lập dữ liệu đó ở bước tiếp nhận request hoặc qua cơ chế context phù hợp. Không đưa dữ liệu nhạy cảm vào context nếu không cần thiết, và không xem việc có một giá trị trong context là thay thế cho kiểm tra quyền.

## 5. Đăng ký DataFetcher cho field lồng nhau

Wiring thủ công không chỉ áp dụng cho root `Query` hoặc `Mutation`. Có thể đăng ký data fetcher cho field của object type:

SDL:

```graphql
type Query {
    book(id: ID!): Book
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

Runtime wiring:

```java
@Bean
RuntimeWiringConfigurer bookFieldWiring(
        BookService bookService,
        AuthorService authorService) {

    return wiringBuilder -> wiringBuilder
        .type("Query", typeWiring -> typeWiring.dataFetcher(
            "book",
            environment -> {
                String id = environment.getArgument("id");
                return bookService.findById(id).orElse(null);
            }
        ))
        .type("Book", typeWiring -> typeWiring.dataFetcher(
            "author",
            environment -> {
                Book book = environment.getSource();
                return authorService.findById(book.authorId()).orElse(null);
            }
        ));
}
```

Trong ví dụ, data fetcher của `Query.book` tải quyển sách, còn data fetcher của `Book.author` dùng source object để tải tác giả. Tên type và field trong `type(...)` phải khớp với schema SDL.

Đối với field đơn giản có thể đọc trực tiếp từ property hoặc getter của Java object, GraphQL Java có thể sử dụng property data fetcher mặc định. Chỉ cần đăng ký data fetcher riêng khi field cần logic, dữ liệu tổng hợp, gọi service hoặc cách truy cập khác với mặc định.

## 6. Wiring scalar và type resolver

### Đăng ký custom scalar

Custom scalar phải được đăng ký với runtime wiring để GraphQL Java biết cách parse input và serialize output. Có thể dùng `RuntimeWiringConfigurer`:

```java
import graphql.scalars.ExtendedScalars;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
public class ScalarRuntimeConfig {

    @Bean
    RuntimeWiringConfigurer scalarWiring() {
        return wiringBuilder -> wiringBuilder
            .scalar(ExtendedScalars.Date)
            .scalar(ExtendedScalars.UUID);
    }
}
```

SDL phải khai báo scalar có tên khớp với implementation đã đăng ký:

```graphql
scalar Date
scalar UUID

type Book {
    id: UUID!
    publishedOn: Date!
}
```

Ví dụ giả định dependency `graphql-java-extended-scalars` đã được thêm với phiên bản tương thích với GraphQL Java mà Spring Boot quản lý. Nếu tự viết scalar, đăng ký `GraphQLScalarType` được tạo từ `Coercing` thay cho các scalar mở rộng.

### Đăng ký TypeResolver cho union

Với interface hoặc union, GraphQL cần xác định object type cụ thể của giá trị Java tại runtime. Ví dụ SDL:

```graphql
union SearchResult = Book | Author

type Query {
    search(term: String!): [SearchResult!]!
}

type Book {
    id: ID!
    title: String!
}

type Author {
    id: ID!
    name: String!
}
```

Có thể đăng ký `TypeResolver`:

```java
@Bean
RuntimeWiringConfigurer searchResultWiring() {
    return wiringBuilder -> wiringBuilder.type(
        "SearchResult",
        typeWiring -> typeWiring.typeResolver(environment -> {
            Object value = environment.getObject();

            if (value instanceof Book) {
                return environment.getSchema().getObjectType("Book");
            }
            if (value instanceof Author) {
                return environment.getSchema().getObjectType("Author");
            }

            throw new IllegalStateException(
                "Unsupported SearchResult type: " + value.getClass().getName()
            );
        })
    );
}
```

`environment.getObject()` là instance Java do data fetcher trả về. `TypeResolver` phải trả về một `GraphQLObjectType` tồn tại trong schema và là thành viên hợp lệ của union. Nếu giá trị Java không thuộc những loại được hỗ trợ, cần báo lỗi rõ ràng thay vì chọn một object type không chính xác.

## 7. DataFetcher có thể trả về kết quả bất đồng bộ

GraphQL Java cho phép data fetcher trả về giá trị trực tiếp hoặc một kiểu bất đồng bộ được hỗ trợ, chẳng hạn `CompletionStage`. Điều này hữu ích khi resolver gọi service bất đồng bộ hoặc client HTTP không blocking.

Ví dụ:

```java
import java.util.concurrent.CompletionStage;

DataFetcher<CompletionStage<Book>> bookFetcher = environment -> {
    String id = environment.getArgument("id");
    return bookService.findByIdAsync(id);
};
```

`findByIdAsync` là phương thức giả định trả về `CompletionStage<Book>`. GraphQL engine chờ kết quả hoàn tất để tiếp tục tạo response. Không nên bọc một lời gọi blocking trong `CompletableFuture.supplyAsync` chỉ để làm chữ ký trông bất đồng bộ; cách đó vẫn chiếm thread trong lúc chờ và có thể tạo áp lực lên thread pool.

Nếu service đang dùng JPA/JDBC blocking, hãy tổ chức execution và thread model nhất quán với stack hiện tại. Nếu ứng dụng dùng reactive stack, nên giữ luồng reactive xuyên suốt thay vì trộn các thao tác blocking không được kiểm soát.

## 8. Kết hợp wiring thủ công với DataLoader

Khi data fetcher của field lồng nhau tải một bản ghi cho từng parent object, ứng dụng có thể gặp N+1. Wiring thủ công không tự giải quyết vấn đề này. Có thể dùng DataLoader để gom các yêu cầu theo batch.

Ví dụ một data fetcher lấy DataLoader đã đăng ký:

```java
DataFetcher<CompletionStage<Author>> authorFetcher = environment -> {
    Book book = environment.getSource();
    DataLoader<String, Author> loader = environment.getDataLoader("authorLoader");
    return loader.load(book.authorId());
};
```

DataLoader có tên `authorLoader` phải được đăng ký trong execution context. Với Spring for GraphQL, `BatchLoaderRegistry` là cơ chế tích hợp phù hợp để đăng ký batch loader theo request. Tên loader, kiểu khóa và kiểu kết quả phải khớp giữa nơi đăng ký và nơi gọi `getDataLoader`.

Ví dụ này chỉ minh họa cách nối DataFetcher với DataLoader; nó không thay thế phần đăng ký batch loader. Cần kiểm tra batch loader trả kết quả đúng thứ tự tương ứng với danh sách khóa, xử lý khóa không tồn tại và không chia sẻ cache request giữa những người dùng không cùng ngữ cảnh quyền.

## 9. Wiring thủ công và annotation controller

Hai cơ chế đều có thể cung cấp data fetcher cho GraphQL engine, nhưng có cách tổ chức khác nhau.

| Tiêu chí | Annotation mapping | Runtime wiring thủ công |
| --- | --- | --- |
| Khai báo | Annotation trên phương thức controller | `RuntimeWiringConfigurer` và `DataFetcher` |
| Phù hợp | Resolver gắn với nghiệp vụ và controller | Thành phần dùng chung hoặc cấu hình GraphQL Java chuyên biệt |
| Truy cập dependency | Constructor injection vào controller | Spring injection vào bean configurer hoặc factory tạo fetcher |
| Field lồng nhau | `@SchemaMapping` | `type("Book", ...).dataFetcher("author", ...)` |
| Scalar và TypeResolver | Có thể cấu hình qua runtime wiring | Đăng ký trực tiếp trong builder |
| Khả năng đọc | Gần với cấu trúc controller | Tập trung cấu hình theo schema type |

Ví dụ annotation mapping:

```java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id).orElse(null);
    }
}
```

Ví dụ programmatic mapping tương đương đã được đăng ký trong `RuntimeWiringConfigurer`. Với một field cụ thể, hãy chọn một cách ánh xạ làm nguồn chính. Có thể kết hợp hai cách trong cùng ứng dụng cho những field khác nhau, đồng thời tránh đăng ký trùng field trong nhiều configurer hoặc controller.

## 10. Khi nào cần tự xây dựng GraphQlSource?

Trong ứng dụng Spring Boot thông thường, auto-configuration tạo `GraphQlSource`, nạp schema resources và áp dụng các `RuntimeWiringConfigurer` do ứng dụng cung cấp. Vì vậy, việc đăng ký một bean `RuntimeWiringConfigurer` là đủ cho hầu hết nhu cầu wiring bổ sung.

Chỉ cân nhắc tự kiểm soát quá trình tạo `GraphQlSource` khi ứng dụng có yêu cầu đặc biệt, ví dụ:

- Dùng tập schema resource khác với cấu hình mặc định.
- Cần tùy chỉnh sâu quy trình parse hoặc xây dựng schema.
- Tích hợp một schema được tạo theo cách riêng hoặc có nhiều nguồn schema cần phối hợp.
- Cần thay thế một phần auto-configuration bằng cấu hình rõ ràng của ứng dụng.

Khi tự tạo `GraphQlSource`, ứng dụng phải bảo đảm schema resources và runtime wiring đều được cấu hình đầy đủ. Cần xem tài liệu của đúng phiên bản Spring for GraphQL đang dùng để chọn builder API tương ứng, vì chữ ký builder có thể thay đổi giữa các phiên bản. Không tạo một `GraphQlSource` bean tùy chỉnh chỉ để thêm một data fetcher đơn giản, vì điều đó có thể làm ứng dụng bỏ qua hoặc thay thế một phần auto-configuration mà nó đang cần.

## 11. Lỗi thường gặp khi wiring thủ công

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Field không có data fetcher | Tên type hoặc field trong wiring không khớp SDL | Đối chiếu `typeName` và field name trong schema |
| DataFetcher không được gọi | Configurer chưa được Spring phát hiện hoặc schema source không dùng configurer đó | Kiểm tra bean registration và cấu hình GraphQlSource |
| Field luôn trả về `null` | `getSource()` hoặc argument không đúng kiểu, service không tìm thấy dữ liệu | Kiểm tra source object, argument và kết quả service |
| Lỗi ép kiểu argument | Kiểu Java không phù hợp với scalar coercion | Dùng kiểu Java tương thích và kiểm thử input |
| Union/interface không phân giải được | Thiếu TypeResolver hoặc trả về object type không hợp lệ | Đăng ký TypeResolver cho abstract type và bao phủ mọi implementation |
| Custom scalar báo lỗi parse/serialize | Scalar chưa được đăng ký hoặc format không nhất quán | Kiểm tra SDL, runtime wiring và coercing |
| Field bị ánh xạ bởi nhiều nơi | Vừa có annotation controller vừa có DataFetcher thủ công cho cùng field | Chọn một cơ chế làm chủ field và bỏ mapping dư |
| DataLoader trả dữ liệu sai thứ tự | Batch loader không ánh xạ kết quả theo đúng danh sách khóa | Bảo đảm kết quả tương ứng từng khóa hoặc dùng mapped batch loader phù hợp |
| Ứng dụng không khởi động sau khi tự tạo GraphQlSource | Cấu hình tùy chỉnh thiếu schema resource hoặc runtime component | Kiểm tra quá trình tạo schema và cân nhắc giữ auto-configuration |

## 12. Kiểm thử runtime wiring

Nên kiểm thử từ schema và operation thực tế thay vì chỉ kiểm tra bean `RuntimeWiringConfigurer` đã được tạo.

Ví dụ dùng `GraphQlTester` để xác nhận data fetcher thủ công hoạt động:

```java
@SpringBootTest
@AutoConfigureHttpGraphQlTester
class ManualWiringTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void bookFieldIsResolvedByRuntimeWiring() {
        graphQlTester.document("""
            query {
                book(id: "book-42") {
                    id
                    title
                }
            }
            """)
            .execute()
            .path("book.id")
            .entity(String.class)
            .isEqualTo("book-42");
    }
}
```

Ví dụ giả định test context đã cấu hình `BookService` hoặc dữ liệu phù hợp. Ngoài response, nên kiểm tra:

- Schema có field và kiểu dữ liệu đúng như SDL.
- DataFetcher nhận đúng argument và source object.
- Scalar parse input và serialize output theo định dạng đã định nghĩa.
- TypeResolver nhận diện mọi implementation của interface/union.
- DataLoader gom các khóa và trả kết quả đúng khi có nhiều parent object.
- Lỗi từ service được chuyển thành GraphQL error theo chính sách của ứng dụng.

Nếu dùng nhiều `RuntimeWiringConfigurer`, cần có kiểm thử tích hợp xác nhận các cấu hình cùng được áp dụng và không có field bị đăng ký chồng chéo.

## 13. Checklist trước khi dùng wiring thủ công

- [ ] Xác định rõ lý do cần runtime wiring thay cho annotation mapping.
- [ ] SDL đã khai báo type và field cần được kết nối.
- [ ] Có bean `RuntimeWiringConfigurer` được Spring phát hiện.
- [ ] Tên type và field trong wiring khớp với schema.
- [ ] DataFetcher xử lý argument, source object và context đúng cách.
- [ ] Dependency nghiệp vụ được inject qua Spring, không tự khởi tạo trong fetcher.
- [ ] Custom scalar và TypeResolver đã được đăng ký nếu schema yêu cầu.
- [ ] Không ánh xạ trùng một field bằng nhiều cơ chế.
- [ ] N+1 được xem xét và DataLoader được đăng ký nếu cần batch loading.
- [ ] Kiểm thử operation qua `GraphQlTester` với dữ liệu thực tế hoặc fixture phù hợp.
- [ ] Chỉ tự tạo `GraphQlSource` khi có nhu cầu cấu hình đặc biệt và đã kiểm tra đúng API phiên bản.

## Kết luận

Wiring thủ công cho phép nối field trong GraphQL schema với `DataFetcher`, `TypeResolver`, custom scalar và các thành phần runtime của GraphQL Java. Trong Spring for GraphQL, `RuntimeWiringConfigurer` là điểm mở rộng tiêu chuẩn để đăng ký những thành phần đó mà vẫn tận dụng quá trình tạo `GraphQlSource` của Spring Boot.

Hãy dùng annotation mapping cho resolver gắn trực tiếp với controller nghiệp vụ và dùng wiring thủ công khi cần cấu hình GraphQL Java ở mức thấp hơn. Với mỗi field, cần xác định rõ một cơ chế ánh xạ, kiểm tra tên type/field, quản lý dependency qua Spring và kiểm thử operation sau khi schema được khởi tạo. Cách tiếp cận này giữ runtime wiring rõ ràng, dễ bảo trì và tương thích với những tính năng khác như scalar, union/interface resolver và DataLoader.
