# GraphQlSourceBuilder trong Spring for GraphQL

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vai trò của `GraphQlSource` và builder trong quá trình khởi tạo GraphQL runtime.
- Phân biệt việc xây dựng schema với việc thực thi từng GraphQL request.
- Biết cách nạp một hoặc nhiều file SDL vào `GraphQlSource`.
- Kết hợp `RuntimeWiringConfigurer` để đăng ký DataFetcher, scalar và type resolver.
- Hiểu các bước gọi `build()` và kết quả runtime được tạo ra.
- Phân biệt `GraphQlSource.Builder`, `GraphQlSourceBuilderCustomizer` và `RuntimeWiringConfigurer`.
- Tùy chỉnh builder trong Spring Boot mà vẫn giữ auto-configuration.
- Nhận biết tác động khi tự tạo bean `GraphQlSource` và thay thế cấu hình mặc định.
- Kiểm thử schema, runtime wiring và chẩn đoán lỗi trong quá trình khởi tạo.

## 1. GraphQlSource là gì?

`GraphQlSource` là abstraction của Spring for GraphQL đại diện cho GraphQL runtime đã được xây dựng từ schema và runtime wiring. Nó cung cấp đối tượng GraphQL đã sẵn sàng để nhận operation thông qua tầng thực thi của Spring GraphQL.

Để tạo `GraphQlSource`, ứng dụng cần kết hợp các thành phần như:

- Schema SDL mô tả type, field, argument, input, enum, interface và union.
- Runtime wiring kết nối field trong schema với DataFetcher, scalar, type resolver và các thành phần thực thi khác.
- Các extension phục vụ xử lý lỗi, instrumentation và những tùy chỉnh runtime nếu ứng dụng cần.

Có thể hình dung quan hệ giữa các thành phần như sau:

~~~mermaid
flowchart TD
    A["Schema SDL resources"] --> D["GraphQlSource builder"]
    B["RuntimeWiringConfigurer"] --> D
    C["Exception resolvers / Instrumentation"] --> D
    D --> E["build()"]
    E --> F["GraphQlSource"]
    F --> G["ExecutionGraphQlService"]
    G --> H["GraphQL request execution"]
~~~

Builder tập hợp cấu hình ở giai đoạn khởi tạo. Sau khi gọi `build()`, ứng dụng nhận được `GraphQlSource` để các thành phần như `ExecutionGraphQlService` sử dụng khi xử lý request.

Cần phân biệt hai thời điểm:

- **Build time:** đọc SDL, tạo schema, áp dụng runtime wiring và xây dựng GraphQL runtime.
- **Request time:** mỗi GraphQL operation được đưa vào runtime đã xây dựng để parse, validate và thực thi.

Không nên tạo lại `GraphQlSource` cho từng request. Schema và runtime wiring thường được xây dựng một lần trong quá trình khởi tạo application context rồi được tái sử dụng.

## 2. GraphQlSource builder giải quyết công việc gì?

Builder giúp lắp ráp GraphQL runtime theo từng bước, thay vì yêu cầu ứng dụng tự tạo toàn bộ đối tượng GraphQL Java.

Một cấu hình thường cần quyết định:

1. Nguồn SDL nào được dùng để tạo schema?
2. Các `RuntimeWiringConfigurer` nào cần được áp dụng?
3. DataFetcher và type resolver nào kết nối với field hoặc abstract type?
4. Custom scalar nào được đăng ký?
5. Exception resolver và instrumentation nào cần được tích hợp?
6. Khi cấu hình hoàn tất, runtime được tạo và công bố dưới dạng bean nào?

Tên API cụ thể có thể thay đổi giữa các phiên bản Spring GraphQL. Trong Spring for GraphQL, điểm vào phổ biến để xây dựng từ file schema là `GraphQlSource.schemaResourceBuilder()`. Builder trả về hỗ trợ khai báo schema resources, cấu hình runtime wiring và tạo `GraphQlSource`.

Tên bài học `GraphQlSourceBuilder` nói đến nhóm API builder dùng để tạo `GraphQlSource`. Trong code Spring GraphQL, điểm vào thường gặp là `GraphQlSource.schemaResourceBuilder()` và các interface builder liên quan; khi dùng Spring Boot, bạn còn có extension point `GraphQlSourceBuilderCustomizer`. Không nên nhầm builder ở giai đoạn khởi tạo với một service xử lý request.

Ví dụ tối giản:

~~~java
GraphQlSource graphQlSource = GraphQlSource.schemaResourceBuilder()
        .schemaResources(
                new ClassPathResource("graphql/schema.graphqls")
        )
        .build();
~~~

Ví dụ này cho thấy cấu trúc cơ bản: chọn resource chứa SDL rồi gọi `build()`. Trong ứng dụng thật, runtime wiring phải được bổ sung để các field nghiệp vụ có DataFetcher phù hợp.

## 3. Nạp schema SDL vào builder

Schema có thể được đặt trong một hoặc nhiều resource. Ví dụ:

~~~text
src/main/resources/
└── graphql/
    ├── schema.graphqls
    ├── book.graphqls
    └── author.graphqls
~~~

Có thể đưa nhiều resource vào builder:

~~~java
@Bean
GraphQlSource graphQlSource() {
    return GraphQlSource.schemaResourceBuilder()
            .schemaResources(
                    new ClassPathResource("graphql/schema.graphqls"),
                    new ClassPathResource("graphql/book.graphqls"),
                    new ClassPathResource("graphql/author.graphqls")
            )
            .build();
}
~~~

Các định nghĩa trong nhiều file được kết hợp thành một schema GraphQL. Việc chia file giúp tổ chức schema theo miền nghiệp vụ, nhưng các type và field vẫn phải tạo thành một schema hợp lệ sau khi kết hợp.

Ví dụ file gốc có root type:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

File `book.graphqls` có thể bổ sung field bằng `extend`:

~~~graphql
type Book {
    id: ID!
    title: String!
}

extend type Query {
    books: [Book!]!
}
~~~

Nếu nhiều file định nghĩa trùng một type hoặc field theo cách không hợp lệ, schema construction có thể thất bại. Hãy dùng `extend` khi muốn mở rộng một type đã có và kiểm tra toàn bộ schema sau khi ghép.

### 3.1. Resource path và classpath

`ClassPathResource` lấy file từ classpath của ứng dụng. Khi đóng gói thành JAR, resource phải được đưa vào artifact để builder đọc được lúc khởi động.

Nếu schema nằm ở filesystem hoặc một nguồn resource khác, có thể dùng implementation `Resource` phù hợp. Không nên hard-code đường dẫn máy phát triển nếu ứng dụng cần chạy ở nhiều môi trường.

Trong Spring Boot, property schema locations thường đủ để cấu hình nơi tìm SDL. Chỉ cần tự chỉ định resource trong builder khi ứng dụng chủ động quản lý `GraphQlSource` hoặc có yêu cầu đặc biệt.

## 4. Runtime wiring được áp dụng như thế nào?

SDL mô tả hợp đồng, nhưng không tự cung cấp dữ liệu cho field. Runtime wiring kết nối field trong schema với thành phần thực thi.

Spring for GraphQL cung cấp `RuntimeWiringConfigurer`, một extension point cho phép bổ sung cấu hình vào `RuntimeWiring.Builder`.

Ví dụ DataFetcher thủ công:

~~~java
@Component
class BookDataFetcher implements DataFetcher<Book> {

    private final BookService bookService;

    BookDataFetcher(BookService bookService) {
        this.bookService = bookService;
    }

    @Override
    public Book get(DataFetchingEnvironment environment) {
        String id = environment.getArgument("id");
        return bookService.findById(id);
    }
}
~~~

Đăng ký DataFetcher:

~~~java
@Bean
RuntimeWiringConfigurer bookRuntimeWiring(BookDataFetcher bookDataFetcher) {
    return wiringBuilder -> wiringBuilder
            .type("Query", typeWiring -> typeWiring
                    .dataFetcher("book", bookDataFetcher));
}
~~~

Trong ví dụ:

- `Query` là root object type trong SDL.
- `book` là field được kết nối với DataFetcher.
- `environment.getArgument("id")` lấy argument mà client truyền.
- DataFetcher trả về giá trị cho field `book`.

Tên type và field phải khớp với SDL. Nếu field không được khai báo hoặc tên bị sai, schema wiring không thể tạo mapping mong muốn.

### 4.1. RuntimeWiringConfigurer khác builder customizer thế nào?

Hai extension point này có liên hệ nhưng có trách nhiệm khác nhau:

| Thành phần | Vai trò |
| --- | --- |
| `RuntimeWiringConfigurer` | Cấu hình GraphQL runtime wiring: DataFetcher, scalar, type resolver và wiring liên quan |
| `GraphQlSourceBuilderCustomizer` | Tùy chỉnh builder dùng để tạo `GraphQlSource` trong Spring Boot |
| `GraphQlSource.Builder` | API builder để khai báo schema resources và cấu hình quá trình tạo source |
| `GraphQlSource` | Runtime source đã được xây dựng, được tầng thực thi sử dụng |

Nếu chỉ cần thêm DataFetcher hoặc scalar, thường nên đăng ký `RuntimeWiringConfigurer`. Không cần tự tạo lại `GraphQlSource` chỉ để bổ sung một field mapping.

## 5. Đăng ký nhiều thành phần runtime

Một GraphQL runtime có thể cần nhiều `RuntimeWiringConfigurer`. Ví dụ:

- Một configurer đăng ký DataFetcher cho Query.
- Một configurer đăng ký custom scalar.
- Một configurer đăng ký type resolver cho interface hoặc union.
- Một configurer đăng ký wiring cho directive tùy chỉnh.

Ví dụ đăng ký scalar:

~~~java
@Bean
RuntimeWiringConfigurer scalarConfigurer() {
    return builder -> builder.scalar(ExtendedScalars.UUID);
}
~~~

Ví dụ đăng ký union resolver:

~~~java
@Bean
RuntimeWiringConfigurer searchResultConfigurer() {
    ClassNameTypeResolver resolver = new ClassNameTypeResolver();
    resolver.addMapping(BookView.class, "Book");
    resolver.addMapping(AuthorView.class, "Author");

    return builder -> builder.type(
            "SearchResult",
            type -> type.typeResolver(resolver)
    );
}
~~~

Spring Boot có thể thu thập các bean `RuntimeWiringConfigurer` và áp dụng chúng trong quá trình xây dựng `GraphQlSource`. Điều này giúp từng nhóm chức năng đóng góp cấu hình mà không phải gom tất cả vào một class khổng lồ.

Khi nhiều configurer cùng tác động đến một type hoặc field, cần bảo đảm chúng không ghi đè hoặc xung đột ngoài ý muốn. Nếu thứ tự có ý nghĩa, hãy dùng cơ chế ordering được Spring hỗ trợ và kiểm thử kết quả wiring cuối cùng.

## 6. Exception resolver và instrumentation

Builder cũng là nơi tích hợp các thành phần ảnh hưởng đến quá trình thực thi.

### 6.1. DataFetcherExceptionResolver

DataFetcher có thể phát sinh exception khi gọi service hoặc truy cập dữ liệu. `DataFetcherExceptionResolver` cho phép ánh xạ exception thành GraphQL error có cấu trúc.

Ví dụ bean resolver:

~~~java
@Component
class BookExceptionResolver extends DataFetcherExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(
            Throwable exception,
            DataFetchingEnvironment environment) {

        if (exception instanceof BookNotFoundException) {
            return GraphqlErrorBuilder.newError(environment)
                    .message("Không tìm thấy sách")
                    .errorType(ErrorType.NOT_FOUND)
                    .build();
        }

        return null;
    }
}
~~~

Trong ứng dụng Spring Boot, các exception resolver được tích hợp qua cấu hình GraphQL tương ứng. Khi tự tạo `GraphQlSource`, phải bảo đảm resolver cần thiết được đưa vào builder theo API của phiên bản đang dùng.

Không nên biến mọi exception thành một lỗi nghiệp vụ giống nhau. Cần phân biệt lỗi không tìm thấy, lỗi validation, lỗi authorization và lỗi hạ tầng để response và log có ý nghĩa.

### 6.2. Instrumentation

GraphQL Java cung cấp `Instrumentation` để quan sát hoặc can thiệp vào vòng đời thực thi GraphQL, chẳng hạn ghi nhận thời gian, theo dõi hoạt động hoặc áp dụng một chính sách runtime.

Ví dụ nhu cầu instrumentation:

- Đo thời gian thực thi operation.
- Thu thập số liệu theo operation name.
- Theo dõi lỗi và trạng thái thực thi.
- Ghi nhận thông tin phục vụ tracing.
- Tích hợp giới hạn hoặc phân tích độ phức tạp query nếu có triển khai phù hợp.

Instrumentation cần được chọn cẩn thận vì nó có thể chạy trên mọi request. Tránh ghi document và variables nguyên vẹn vào log nếu chúng có thể chứa token hoặc dữ liệu nhạy cảm.

Builder hỗ trợ tích hợp instrumentation theo API GraphQL Java/Spring GraphQL tương ứng với phiên bản. Trong ứng dụng Boot, ưu tiên extension point được phiên bản Boot hỗ trợ thay vì tự tạo source chỉ để gắn một instrumentation.

## 7. Tạo GraphQlSource thủ công

Trong một số ứng dụng không dùng auto-configuration hoặc cần tự quản lý toàn bộ GraphQL runtime, có thể khai báo bean `GraphQlSource` bằng builder.

Ví dụ:

~~~java
@Configuration
class ManualGraphQlSourceConfiguration {

    @Bean
    GraphQlSource graphQlSource(BookDataFetcher bookDataFetcher) {
        return GraphQlSource.schemaResourceBuilder()
                .schemaResources(
                        new ClassPathResource("graphql/schema.graphqls")
                )
                .configureRuntimeWiring(builder -> builder
                        .type("Query", type -> type
                                .dataFetcher("book", bookDataFetcher)))
                .build();
    }
}
~~~

Đây là ví dụ lắp ráp thủ công tối giản. Khi tự quản lý source, ứng dụng phải chịu trách nhiệm cung cấp đầy đủ wiring cần thiết: annotated controller configurer nếu dùng `@QueryMapping`/`@SchemaMapping`, scalar, type resolver, exception resolver, instrumentation và các extension khác mà hệ thống cần.

Nếu ứng dụng dùng Spring Boot, việc tự đăng ký bean `GraphQlSource` thường khiến auto-configuration lùi lại do bean mặc định đã được thay thế. Các bean nền tảng khác có thể vẫn tồn tại, nhưng source tự tạo phải được cấu hình để sử dụng chúng đúng cách.

Vì vậy, chỉ nên tự tạo source khi thực sự cần kiểm soát quá trình xây dựng runtime. Với nhu cầu thông thường, hãy để Boot tạo `GraphQlSource` và bổ sung các configurer hoặc customizer chuyên biệt.

## 8. GraphQlSourceBuilderCustomizer trong Spring Boot

Spring Boot cung cấp `GraphQlSourceBuilderCustomizer` để ứng dụng điều chỉnh builder trước khi `GraphQlSource` được tạo.

Ví dụ:

~~~java
import graphql.scalars.ExtendedScalars;
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class GraphQlSourceCustomization {

    @Bean
    GraphQlSourceBuilderCustomizer uuidSourceCustomizer() {
        return builder -> builder.configureRuntimeWiring(
                wiringBuilder -> wiringBuilder.scalar(ExtendedScalars.UUID)
        );
    }
}
~~~

Customizer nhận builder do auto-configuration đang sử dụng và bổ sung cấu hình. Spring Boot tiếp tục chịu trách nhiệm xây dựng source theo cấu hình chung.

Tuy nhiên, nếu mục tiêu chỉ là đăng ký scalar, một bean `RuntimeWiringConfigurer` thường rõ trách nhiệm hơn:

~~~java
@Bean
RuntimeWiringConfigurer uuidScalarConfigurer() {
    return builder -> builder.scalar(ExtendedScalars.UUID);
}
~~~

Chọn `GraphQlSourceBuilderCustomizer` khi cần thay đổi ở cấp builder, ví dụ cấu hình schema resource hoặc một tùy chọn builder mà configurer runtime wiring không thể diễn đạt. Chọn `RuntimeWiringConfigurer` cho các thay đổi thuần runtime wiring.

API cụ thể của customizer và builder phụ thuộc phiên bản Spring Boot/Spring GraphQL. Hãy kiểm tra chữ ký API trong phiên bản dự án trước khi dùng các method bổ sung.
## 9. SchemaFactory và xử lý schema nâng cao

Trong trường hợp schema cần được tạo theo quy tắc đặc biệt, builder có thể được cấu hình với một schema factory phù hợp với API phiên bản đang sử dụng.

Một schema factory có thể hữu ích khi ứng dụng cần:

- Kết hợp hoặc biến đổi định nghĩa schema theo một quy trình riêng.
- Áp dụng quy tắc xây dựng schema dùng chung.
- Tích hợp một nguồn schema được quản lý ngoài classpath.
- Kiểm soát việc tạo `GraphQLSchema` trước khi GraphQL runtime được dựng.

Không nên chọn schema factory chỉ để thêm một DataFetcher hoặc scalar. Các nhu cầu đó đã có `RuntimeWiringConfigurer`.

Nếu schema được tạo động từ metadata bên ngoài, cần kiểm soát nguồn dữ liệu, tính ổn định và thời điểm refresh. Việc thay schema runtime khi ứng dụng đang phục vụ request cần có chiến lược đồng bộ rõ ràng; không nên sửa schema dùng chung một cách tùy tiện.

## 10. Builder lifecycle và cấu hình một lần

Builder là đối tượng cấu hình tạm thời trong giai đoạn khởi tạo. Sau khi gọi `build()`, kết quả là `GraphQlSource` đã được tạo.

Một vòng đời điển hình:

1. Spring khởi tạo các bean cấu hình và configurer.
2. Auto-configuration hoặc cấu hình ứng dụng tạo builder.
3. Builder nhận schema resources.
4. Runtime wiring configurers được áp dụng.
5. Các extension cần thiết được kết nối.
6. `build()` tạo `GraphQlSource`.
7. Execution service sử dụng source để thực thi request.

Không nên giữ builder trong một singleton rồi thay đổi cấu hình theo từng request. Làm như vậy có thể dẫn đến trạng thái dùng chung không nhất quán hoặc race condition.

Nếu ứng dụng cần thay đổi schema khi chạy, hãy thiết kế một quy trình refresh có kiểm soát và tạo source mới theo cơ chế được hỗ trợ. Không nên sửa builder hoặc schema runtime đang được nhiều request sử dụng.

## 11. Kiểm thử GraphQlSource và runtime wiring

Có thể kiểm tra `GraphQlSource` ở nhiều mức.

### 11.1. Kiểm thử schema được tạo

Kiểm tra schema có chứa type và field mong đợi:

~~~java
@Test
void graphQlSourceContainsBookType() {
    GraphQlSource source = graphQlSource();

    assertThat(source.schema().getObjectType("Book"))
            .isNotNull();
}
~~~

Ví dụ này minh họa kiểm tra schema. Trong test thực tế, nên lấy bean từ Spring test context hoặc tạo source qua factory/configuration đang được kiểm thử.

### 11.2. Kiểm thử runtime wiring qua operation

Kiểm thử execution thường hữu ích hơn việc chỉ kiểm tra bean tồn tại:

~~~java
graphQlTester.document("""
        query FindBook($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
        .variable("id", "book-42")
        .execute()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Spring GraphQL");
~~~

Test này xác minh schema, DataFetcher hoặc controller mapping và quá trình thực thi được kết nối với nhau.

### 11.3. Kiểm thử các điều kiện lỗi

Nên có test cho:

- Resource SDL không tồn tại.
- SDL sai cú pháp hoặc định nghĩa type không hợp lệ.
- Field không có DataFetcher hoặc property phù hợp.
- Scalar chưa được đăng ký.
- TypeResolver không xác định được object type.
- Exception resolver ánh xạ lỗi đúng.
- Instrumentation được gọi và không làm thay đổi response ngoài dự kiến.

Với lỗi xảy ra trong quá trình khởi tạo context, kiểm tra nguyên nhân gốc trong exception chain và condition report thay vì chỉ nhìn thông báo tổng quát rằng ứng dụng không khởi động.

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `GraphQlSource` không khởi tạo | Resource SDL không tồn tại hoặc schema không hợp lệ | Kiểm tra resource path và lỗi parse/validation |
| Field có trong SDL nhưng không chạy resolver | Runtime wiring chưa đăng ký DataFetcher/controller mapping | Kiểm tra `RuntimeWiringConfigurer` và annotated controller configurer |
| Custom scalar báo unknown type hoặc coercion error | Scalar chưa được khai báo hoặc chưa được đăng ký đúng | Kiểm tra SDL và runtime wiring |
| Union/interface không resolve được object type | Thiếu hoặc sai `TypeResolver` | Kiểm tra mapping class-to-type |
| Boot không tạo source mặc định | Ứng dụng đã đăng ký bean `GraphQlSource` riêng | Kiểm tra bean override và cấu hình thủ công |
| Một configurer không có tác dụng | Configurer không được Spring quản lý hoặc không được truyền vào builder | Kiểm tra bean registration và custom source setup |
| Schema nhiều file bị lỗi | Định nghĩa trùng hoặc dùng `extend` sai | Kiểm tra toàn bộ schema sau khi ghép |
| Runtime hoạt động khác giữa các môi trường | Resource hoặc dependency khác nhau | Kiểm tra artifact, classpath và effective configuration |
| Thay đổi builder khi request đang chạy gây lỗi | Dùng chung builder mutable hoặc refresh không đồng bộ | Chỉ build source ở startup hoặc dùng quy trình refresh riêng |

## 13. Quy trình lựa chọn extension point

Khi cần thay đổi GraphQL runtime, hãy chọn extension point theo nhu cầu:

| Nhu cầu | Thành phần nên dùng |
| --- | --- |
| Thêm DataFetcher thủ công | `RuntimeWiringConfigurer` |
| Thêm custom scalar | `RuntimeWiringConfigurer` |
| Ánh xạ interface hoặc union | `RuntimeWiringConfigurer` |
| Tùy chỉnh cách tạo GraphQlSource trong Boot | `GraphQlSourceBuilderCustomizer` |
| Tự quản lý schema resources và runtime | `GraphQlSource.schemaResourceBuilder()` |
| Xử lý lỗi từ DataFetcher | `DataFetcherExceptionResolver` |
| Quan sát vòng đời GraphQL execution | GraphQL Java `Instrumentation` |
| Xử lý nghiệp vụ của field | `@QueryMapping`, `@MutationMapping`, `@SchemaMapping` |

Một quy tắc thực tế là chọn extension point hẹp nhất đáp ứng được yêu cầu. Điều này giúp cấu hình dễ đọc, tránh thay thế hạ tầng mặc định không cần thiết và giảm rủi ro bỏ sót các thành phần mà Spring Boot đã tích hợp.

## 14. Tổng kết

`GraphQlSource` đại diện cho GraphQL runtime đã được xây dựng từ SDL, runtime wiring và các extension liên quan. Builder giúp nạp schema resources, áp dụng DataFetcher, scalar, type resolver, exception resolver và instrumentation trước khi tạo source bằng `build()`.

Trong ứng dụng Spring Boot, hãy ưu tiên `RuntimeWiringConfigurer` cho DataFetcher và scalar, `GraphQlSourceBuilderCustomizer` cho tùy chỉnh builder, và để auto-configuration tạo `GraphQlSource` mặc định. Chỉ tự tạo source khi cần quản lý toàn bộ quá trình xây dựng runtime và đã bảo đảm các configurer cần thiết được kết nối. Kiểm thử bằng operation GraphQL thực tế giúp xác nhận schema và wiring hoạt động cùng nhau như mong đợi.


